import os, stripe, traceback, edge_tts, asyncio, uuid, time, tempfile
from flask import Flask, request, send_file, render_template, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
import smtplib
from email.mime.text import MIMEText
import random
import gdown



# Configurații email (modifică cu datele tale)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'bitgaming225@gmail.com'
app.config['MAIL_PASSWORD'] = 'sbfy voly opeb giyo'
# Config DB și bcrypt
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Config Stripe (setează corect cheile tale)
stripe.api_key = "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"
app.config['STRIPE_PRICE_ID'] = 'price_1RIxeUGvoNbZDo5jSTbaavOG'  # înlocuiește cu Price ID-ul tău

# Modelul User cu câmpul premium
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)  # <-- obligatoriu
    password = db.Column(db.String(150), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    confirmed = db.Column(db.Boolean, default=False)
    confirmation_code = db.Column(db.String(6))



with app.app_context():
    db.create_all()
progress_data={}
# Ruta pentru progres
@app.route('/progress')
def get_progress():
    user_id = session.get('user_id')
    if user_id:
        return jsonify(progress=progress_data.get(user_id, 0))
    return jsonify(progress=0)

def update_progress(value):
    user_id = session.get('user_id')
    if user_id:
        progress_data[user_id] = value

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

@app.route('/index')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("index.html", email=session['email'])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            if not existing_user.confirmed:
                db.session.delete(existing_user)
                db.session.commit()
            else:
                return "Email already exists!"
        try:
            code = str(random.randint(100000, 999999))
            new_user = User(
                email=email,
                password=password,
                confirmation_code=code,
                confirmed=False
            )
            db.session.add(new_user)
            db.session.commit()
            
            print(f"[DEBUG] Cod generat: {code}")  # Verificare cod
            
            # Construiește mesajul email
            msg = MIMEText(f'Codul tău de verificare NEON AI este: <strong>{code}</strong>', 'html')
            msg['Subject'] = '🔑 Cod verificare NEON AI'
            msg['From'] = app.config['MAIL_USERNAME']
            msg['To'] = email
            
            # Trimite email
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.send_message(msg)
                print(f"[DEBUG] Email trimis către {email}")  # Confirmare trimitere

            return redirect(url_for('verify_email', email=email))
            
        except Exception as e:
            db.session.rollback()
            print(f"[EROARE] Email nu a putut fi trimis: {str(e)}")  # Log detaliat
            return f"Eroare la trimitere cod: {str(e)}", 500

    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify_email():
    if request.method == 'POST':
        # Schimbă aici: request.args -> request.form
        email = request.form.get('email')
        entered_code = request.form['code']
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.confirmation_code == entered_code:
            user.confirmed = True
            user.confirmation_code = None  # Șterge codul după verificare
            db.session.commit()
            return redirect(url_for('login'))
        return "Invalid code!", 400

    return render_template('verify_email.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.check_password_hash(user.password, password):
            return "Invalid Credentials!", 401
            
        if not user.confirmed:
            return "Unconfirmed account, check your email.", 401

        session['user_id'] = user.id
        session['email'] = user.email
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))
@app.route('/create-checkout-session')
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': app.config['STRIPE_PRICE_ID'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('index', _external=True),
            metadata={'user_id': session.get('user_id')}
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return f"Stripe Error: {str(e)}", 500

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    if session_id:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            user_id = checkout_session.metadata.get('user_id')
            user = User.query.get(int(user_id)) if user_id else None
            if user:
                user.is_premium = True
                db.session.commit()
                session['user_id'] = user.id  # Reînnoiește sesiunea
        except Exception as e:
            print(f"Error upgradinng: {str(e)}")
    return redirect(url_for('index'))

@app.route('/cancel')
def cancel():
    return redirect(url_for('index'))
@app.route('/generate_video', methods=['POST'])
def generate_video():
    try:
        update_progress(0)
        sentence = request.form['text']
        print("Text primit:", sentence)

        # Generare audio
        async def generate_audio():
            communicate = edge_tts.Communicate(sentence, "en-CA-LiamNeural")
            await communicate.save(temp_audio_path)
        session['request_id'] = str(uuid.uuid4())
        
        # Căi unice pentru fișiere
        temp_audio_path = f"static/temp_audio_{session['request_id']}.mp3"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(generate_audio())
        update_progress(20)

        # Procesare audio
        audio = AudioFileClip(temp_audio_path)
        audio_duration = audio.duration

        # Procesare text
        def split_text(text, max_length=20):
            words = text.split(' ')
            chunks = []
            current_chunk = ""
            
            for word in words:
                if len(current_chunk) + len(word) + 1 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = word
                    else:
                        chunks.append(word[:max_length])
                        current_chunk = word[max_length:]
                else:
                    current_chunk += " " + word if current_chunk else word
            
            if current_chunk:
                chunks.append(current_chunk)
            
            return chunks

        chunks = split_text(sentence)
        update_progress(40)

        # Creare text clips
        total_chars = sum(len(chunk) for chunk in chunks)
        text_clips = []
        start_time = 0
        
        for chunk in chunks:
            chunk_duration = (len(chunk) / total_chars) * audio_duration
            
            txt_clip = TextClip(
                text=chunk,
                font='impact',
                font_size=100,
                color='#FF69B4',
                size=(1200, None),
                stroke_color='#FF1493',
                stroke_width=5,
                transparent=True,
                method='caption',
                text_align='center',
            ).with_duration(chunk_duration).with_start(start_time).with_position('center')
            text_clips.append(txt_clip)
            start_time += chunk_duration

        update_progress(60)
        DRIVE_FILE_ID = "1VTH0cSEJpBKJcHPAjUfZs5cmirQh9Jc4"
        download_url = f"https://drive.google.com/uc?export=download&id={DRIVE_FILE_ID}"
        temp_video_path = f"static/temp_video_{session['request_id']}.mp4"
        segment_duration = audio_duration + 1
        if not os.path.exists(temp_video_path):
            gdown.download(download_url, temp_video_path, quiet=False)
        # Încărcare gameplay
        try:
            gameplay = VideoFileClip(temp_video_path).subclipped(0, audio_duration)
        except Exception as e:
            print(f"Eroare la încărcarea videoclipului Drive:  {e}")
            return "Eroare la încărcarea videoclipului", 500
        user = User.query.get(session.get('user_id'))
        if user and user.is_premium:
            final = CompositeVideoClip([gameplay] + text_clips).with_audio(audio)
        else:
            watermark = TextClip(text="CikaBot", font='impact', font_size=100,
                                color='white', stroke_color='black', stroke_width=2)
            watermark = (watermark
                        .with_opacity(0.5)
                        .with_duration(audio_duration)
                        .with_position('top'))
            final = CompositeVideoClip([gameplay, watermark] + text_clips).with_audio(audio)
        update_progress(80)
        # Salvare video
        output_path = f"static/generated_video_{session['request_id']}.mp4"
        final.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')
        update_progress(100)

        response = send_file(output_path, as_attachment=True)
        response.call_on_close(lambda: cleanup_files(temp_audio_path, output_path))
        return response
    except Exception as e:
        print("Error:", e)
        print("Error details:", traceback.format_exc())
        return f"Error: {str(e)}", 500
    finally:
        time.sleep(2)
        update_progress(0)
def cleanup_files(*paths):
    for path in paths:
        try:
            os.remove(temp_path)
            print(f"[CLEANUP] Șters: {path}")
        except: pass


def delete_temp_files():
    temp_dir = tempfile.gettempdir()
    for fname in os.listdir(temp_dir):
        if fname.startswith(('temp_audio_', 'generated_video_')):
            try:
                os.remove(os.path.join(temp_dir, fname))
            except:
                pass
if __name__ == '__main__':
    if not os.path.exists("static"):
        os.makedirs("static")
    app.run(host="0.0.0.0", port=8000)
