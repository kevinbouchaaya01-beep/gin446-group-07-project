import os, secrets, sqlite3, datetime as dt, functools, json, urllib.request
from flask import Flask, render_template, request, redirect, url_for, session, g, abort, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
app=Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32), DATABASE=os.environ.get('DATABASE_PATH','medora.db'), MAX_CONTENT_LENGTH=1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE')=='1')
def db():
    if 'db' not in g:
        g.db=sqlite3.connect(app.config['DATABASE']); g.db.row_factory=sqlite3.Row; g.db.execute('PRAGMA foreign_keys=ON')
    return g.db
@app.teardown_appcontext
def close(e):
    if 'db' in g: g.db.close()
def init():
    d=db(); d.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('patient','doctor','assistant','admin')),specialty TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS slots(id INTEGER PRIMARY KEY,doctor INTEGER REFERENCES users(id),start TEXT NOT NULL,UNIQUE(doctor,start));
    CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY,slot INTEGER REFERENCES slots(id),patient INTEGER REFERENCES users(id),status TEXT NOT NULL DEFAULT 'Booked',created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE UNIQUE INDEX IF NOT EXISTS one_booking ON appointments(slot) WHERE status!='Cancelled';'''); d.commit()
    if os.environ.get('DEMO_MODE','0')=='1':
        d.execute(
            "UPDATE users SET email=? WHERE email=? "
            "AND role='doctor' AND specialty='Cardiology' "
            "AND NOT EXISTS (SELECT 1 FROM users WHERE email=?)",
            ('cardio@medora.test', 'doctor@medora.test', 'cardio@medora.test')
        )

        for name,email,role,specialty in [('Sarah Haddad','cardio@medora.test','doctor','Cardiology'),('Adam Khoury','eye@medora.test','doctor','Ophthalmology'),('Lina Saad','general@medora.test','doctor','General Medicine'),('Reception','assistant@medora.test','assistant',''),('Clinic Admin','admin@medora.test','admin',''),('Demo Patient','patient@medora.test','patient','')]:
            if not d.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone(): d.execute('INSERT INTO users(name,email,password,role,specialty) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(os.environ['DEMO_PASSWORD']),role,specialty))
        for u in d.execute("SELECT id FROM users WHERE role='doctor'").fetchall():
            for day in range(7):
                date=dt.date.today()+dt.timedelta(days=day)
                for hour in (9,10,11,14,15):
                    d.execute('INSERT OR IGNORE INTO slots(doctor,start) VALUES(?,?)',(u['id'],f'{date}T{hour:02}:00'))
        d.commit()
@app.before_request
def before():
    g.user=db().execute('SELECT id,name,email,password,role,specialty FROM users WHERE id=?',(session.get('uid'),)).fetchone()
    if 'csrf' not in session: session['csrf']=secrets.token_hex(24)
    if request.method=='POST' and not secrets.compare_digest(session['csrf'],request.form.get('csrf','') or request.headers.get('X-CSRF-Token','')): abort(400)
def roles(*allowed):
    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*a,**k):
            if not g.user: return redirect(url_for('login'))
            if g.user['role'] not in allowed: abort(403)
            return fn(*a,**k)
        return wrapped
    return deco
@app.route('/')
def home(): return redirect(url_for('dashboard')) if g.user else render_template('home.html')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=db().execute('SELECT * FROM users WHERE email=?',(request.form.get('email','').strip().lower(),)).fetchone()
        if u and check_password_hash(u['password'],request.form.get('password','')):
            session.clear(); session['uid']=u['id']; return redirect(url_for('dashboard'))
        flash('Invalid email or password.')
    return render_template('login.html',register=False)
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); pw=request.form.get('password','')
        if not name or len(name)>100 or '@' not in email or len(email)>200 or not 10<=len(pw)<=128: flash('Enter a valid name, email and password (10–128 characters).')
        else:
            try:
                cur=db().execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',(name,email,generate_password_hash(pw),'patient')); db().commit(); session.clear(); session['uid']=cur.lastrowid; return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError: flash('Email already registered.')
    return render_template('login.html',register=True)
@app.post('/logout')
def logout(): session.clear(); return redirect(url_for('home'))
def appointments():
    sql='SELECT a.id,a.status,s.start,d.name doctor,p.name patient, s.doctor doctor_id FROM appointments a JOIN slots s ON s.id=a.slot JOIN users d ON d.id=s.doctor JOIN users p ON p.id=a.patient'; role=g.user['role']; args=[]
    if role=='patient': sql+=' WHERE a.patient=?'; args=[g.user['id']]
    if role=='doctor': sql+=' WHERE s.doctor=?'; args=[g.user['id']]
    return [dict(r) for r in db().execute(sql+' ORDER BY s.start',args)]

# JavaScript calculates the counters from the authorized appointment list.
STAT_LABELS = {
    'patient': ['Upcoming', 'Completed', 'Cancelled'],
    'doctor': ["Today's visits", 'Waiting', 'Completed'],
    'assistant': ['Active appointments', 'Waiting room', 'Completed'],
    'admin': ['Active appointments', 'Waiting room', 'Completed']
}

@app.get('/dashboard')
@roles('patient','doctor','assistant','admin')
def dashboard():
    doctors=db().execute("SELECT id,name,specialty FROM users WHERE role='doctor'").fetchall(); patients=db().execute("SELECT id,name FROM users WHERE role='patient'").fetchall() if g.user['role'] in ('assistant','admin') else []
    staff=db().execute('SELECT id,name,email,role,specialty FROM users ORDER BY role').fetchall() if g.user['role']=='admin' else []
    return render_template('dashboard.html', doctors=doctors, patients=patients, staff=staff, stats=STAT_LABELS[g.user['role']])
@app.get('/api/appointments')
@roles('patient','doctor','assistant','admin')
def api_appointments(): return jsonify(appointments())
# Shared query for both manual and Gemini booking.
def available_slots():
    return [dict(row) for row in db().execute("""
        SELECT s.id, s.start, u.name, u.specialty, s.doctor
        FROM slots s JOIN users u ON u.id=s.doctor
        WHERE s.start>=? AND NOT EXISTS(
            SELECT 1 FROM appointments a
            WHERE a.slot=s.id AND a.status!='Cancelled')
        ORDER BY s.start
    """, (dt.datetime.now().isoformat(timespec='minutes'),))]

@app.get('/api/slots')
@roles('patient','assistant','admin')
def slots():
    doctor = request.args.get('doctor', type=int)
    return jsonify([s for s in available_slots() if s['doctor']==doctor])

@app.post('/book')
@roles('patient','assistant','admin')
def book():
    slot=request.form.get('slot',type=int); patient=g.user['id'] if g.user['role']=='patient' else request.form.get('patient',type=int)
    if not db().execute("SELECT 1 FROM users WHERE id=? AND role='patient'",(patient,)).fetchone() or not db().execute('SELECT 1 FROM slots WHERE id=? AND start>=?',(slot,dt.datetime.now().isoformat(timespec='minutes'))).fetchone(): abort(400)
    try: db().execute('INSERT INTO appointments(slot,patient) VALUES(?,?)',(slot,patient)); db().commit(); flash('Appointment booked.')
    except sqlite3.IntegrityError: flash('That slot is already booked. Choose another.')
    return redirect(url_for('dashboard'))

@app.post('/appointment/<int:id>/status')
@roles('patient','doctor','assistant','admin')
def status(id):
    a=db().execute('SELECT a.*,s.doctor FROM appointments a JOIN slots s ON s.id=a.slot WHERE a.id=?',(id,)).fetchone(); role=g.user['role']; new=request.form.get('status')
    if not a: abort(404)
    if role=='patient' and a['patient']!=g.user['id'] or role=='doctor' and a['doctor']!=g.user['id']: abort(403)
    allowed={'patient':{'Booked':['Cancelled'],'Confirmed':['Cancelled']},'assistant':{'Booked':['Confirmed','Cancelled'],'Confirmed':['Waiting','Cancelled']},'doctor':{'Waiting':['In consultation'],'In consultation':['Completed']},'admin':{'Booked':['Confirmed','Cancelled'],'Confirmed':['Waiting','Cancelled'],'Waiting':['In consultation'],'In consultation':['Completed']}}
    if new not in allowed[role].get(a['status'],[]): abort(400)
    db().execute('UPDATE appointments SET status=? WHERE id=? AND status=?',(new,id,a['status'])); db().commit(); return redirect(url_for('dashboard'))
@app.post('/availability')
@roles('doctor','assistant','admin')
def availability():
    doctor=g.user['id'] if g.user['role']=='doctor' else request.form.get('doctor',type=int)
    try: start=dt.datetime.fromisoformat(request.form['start']); assert start>dt.datetime.now() and start.minute in (0,30) and start.second==0
    except (ValueError,KeyError,AssertionError,TypeError): abort(400)
    if not db().execute("SELECT 1 FROM users WHERE id=? AND role='doctor'",(doctor,)).fetchone(): abort(400)
    db().execute('INSERT OR IGNORE INTO slots(doctor,start) VALUES(?,?)',(doctor,start.isoformat(timespec='minutes'))); db().commit(); flash('Availability saved.'); return redirect(url_for('dashboard'))
@app.post('/staff')
@roles('admin')
def staff():
    role=request.form.get('role'); name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); pw=request.form.get('password',''); specialty=request.form.get('specialty','').strip()
    if role not in ('doctor','assistant') or not name or '@' not in email or not 10<=len(pw)<=128 or (role=='doctor' and not specialty): abort(400)
    try: db().execute('INSERT INTO users(name,email,password,role,specialty) VALUES(?,?,?,?,?)',(name,email,generate_password_hash(pw),role,specialty)); db().commit(); flash('Staff account created.')
    except sqlite3.IntegrityError: flash('Email already exists.')
    return redirect(url_for('dashboard'))
@app.post('/api/smart')
@roles('patient','assistant','admin')
def smart():
    key=os.environ.get('GEMINI_API_KEY'); text=(request.get_json(silent=True) or {}).get('text','')
    if not isinstance(text,str) or not 1<=len(text)<=500: return jsonify(error='Enter a scheduling request (up to 500 characters).'),400
    if not key: return jsonify(error='Gemini is not configured. Use manual booking.'),503
    specialties=[r[0] for r in db().execute("SELECT DISTINCT specialty FROM users WHERE role='doctor'")]
    prompt=f'Extract only explicitly requested appointment scheduling preferences, never diagnose or infer a specialty from symptoms. Today is {dt.date.today()}. Allowed specialties: {specialties}. Return JSON with specialty (or null), date (YYYY-MM-DD or null), period (morning, afternoon or null). Request: {text}'
    try:
        req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+os.environ.get('GEMINI_MODEL','gemini-2.5-flash')+':generateContent',data=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseMimeType':'application/json'}}).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key}); result=json.loads(urllib.request.urlopen(req,timeout=15).read()); prefs=json.loads(result['candidates'][0]['content']['parts'][0]['text']); spec=prefs.get('specialty'); date=prefs.get('date'); period=prefs.get('period')
        if spec is not None and spec not in specialties or period not in (None,'morning','afternoon'): raise ValueError()
        if date is not None: dt.date.fromisoformat(date)
        matches = [s for s in available_slots()
                   if (not spec or s['specialty']==spec)
                   and (not date or s['start'].startswith(date))
                   and (not period or (int(s['start'][11:13])<12)==(period=='morning'))]
        return jsonify(matches=matches[:10])
    except Exception: return jsonify(error='AI service unavailable or returned invalid data. Use manual booking.'),502
with app.app_context(): init()
if __name__=='__main__': app.run(port=5000)
