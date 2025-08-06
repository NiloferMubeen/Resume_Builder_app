import os
import logging
from resume_parser import main as parse_resume
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from ats_scoring import extract_text,get_mock_data, generate_prompt, analyze_ats_with_gemini


# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Setup
app = Flask(__name__)
app.secret_key = 'my_secret_key'
load_dotenv()

# Debug: Check if API key is loaded
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.error("GEMINI_API_KEY not found in environment variables")
else:
    logger.info(f"GEMINI_API_KEY loaded: {api_key[:10]}...")

# Configure upload folder 
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/resume-options')
def resume_options():
    return render_template('resume-options.html')

@app.route('/upload-resume', methods=['GET'])
def upload_resume():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload():
    try:
        logger.info("Upload request received")

        if 'resume' not in request.files:
            logger.error("No file in request")
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['resume']

        if file.filename == '':
            logger.error("Empty filename")
            return jsonify({'error': 'No file selected'}), 400

        if file:
            original_filename = file.filename
            secured_filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], secured_filename)

            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(path)
            logger.info(f"File saved as: {secured_filename} (original: {original_filename})")
            session['resume_path'] = path
            return jsonify({
                'success': True,
                'filename': secured_filename,
                'originalName': original_filename
            }), 200
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': 'Upload failed'}), 500


@app.route('/templates.html')
def templates():
    return render_template('templates.html')

@app.route('/download.html')
def download():
    session_id = request.args.get('session')
    return render_template('download.html', session=session_id)

@app.route('/build-resume')
def build_resume():
    from_upload = request.args.get('from_upload', 'false').lower() == 'true'
    resume_path = session.get('resume_path') if from_upload else None
    if resume_path:
        parsed = parse_resume(resume_path) if resume_path else {}
        session.pop('resume_path')
        return render_template('build-resume.html', data=parsed)
    return render_template('build-resume.html', data={})


@app.route('/ats-score')
def ats_score():
    file_param = request.args.get('file')
    enhanced_param = request.args.get('enhanced')
    return render_template('ats-score.html', file=file_param, enhanced=enhanced_param)

@app.route('/api/analyze-ats', methods=['POST'])
def analyze_ats():
    try:
        logger.info("ATS analysis request received")

        data = request.get_json()
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No data provided'}), 400

        file_name = data.get('fileName')
        if not file_name:
            logger.error("No fileName in request data")
            return jsonify({'error': 'No file name provided'}), 400

        logger.info(f"Analyzing file: {file_name}")

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)

        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            try:
                files = os.listdir(app.config['UPLOAD_FOLDER'])
                logger.info(f"Files in upload directory: {files}")
            except:
                logger.error("Could not list upload directory")
            return jsonify({'error': 'File not found on server'}), 404

        resume_text = extract_text(file_path)

        if not resume_text or resume_text == 'Unsupported file type':
            logger.error(f"Failed to extract text from file: {file_name}")
            return jsonify({'error': 'Could not extract text from file'}), 400

        logger.info(f"Extracted text length: {len(resume_text)} characters")

        if not api_key:
            logger.error("Gemini API key not configured")
            return jsonify(get_mock_data())

        prompt = generate_prompt(resume_text)
        parsed = analyze_ats_with_gemini(prompt)
        logger.info(f"Parsed response successfully")
        return jsonify(parsed)

    except Exception as e:
        logger.error(f"General error in analyze_ats: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(debug=True)
