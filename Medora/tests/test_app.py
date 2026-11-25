import pytest
from app import app, init

TEST_PASSWORD = 'LocalTestOnly123!'

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DEMO_MODE', '1')
    monkeypatch.setenv('DEMO_PASSWORD', TEST_PASSWORD)
    app.config.update(TESTING=True, DATABASE=str(tmp_path/'test.db'))
    with app.app_context():
        init()
    return app.test_client()

def login(c, email):
    c.get('/login')
    with c.session_transaction() as s:
        token = s['csrf']
    return c.post('/login', data={
        'csrf': token,
        'email': email,
        'password': TEST_PASSWORD
    }, follow_redirects=True)

def test_roles(client):
    assert login(client, 'patient@medora.test').status_code == 200
    with client.session_transaction() as s:
        token = s['csrf']
    assert client.post('/staff', data={'csrf': token}).status_code == 403
    assert client.post('/book', data={}).status_code == 400

def test_booking(client):
    login(client, 'patient@medora.test')
    from app import db
    with app.app_context():
        doctor = db().execute(
            "SELECT id FROM users WHERE email='cardio@medora.test'"
        ).fetchone()[0]
    slot = client.get('/api/slots?doctor='+str(doctor)).json[0]['id']
    with client.session_transaction() as s:
        token = s['csrf']
    for _ in range(2):
        client.post('/book', data={'csrf': token, 'slot': slot})
    assert len(client.get('/api/appointments').json) == 1