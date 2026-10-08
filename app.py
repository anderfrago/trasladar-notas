import hmac
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

import click
import google_auth_httplib2
import httplib2
from dotenv import load_dotenv
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from logic import InputError, TransferGrades
from storage import Store

SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.file']

def create_app(config=None):
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / '.env')
    client_secrets = Path(os.getenv('GOOGLE_CLIENT_SECRETS', 'oauth_credentials.json')).expanduser()
    if not client_secrets.is_absolute():
        client_secrets = project_dir / client_secrets
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', ''), TOKEN_ENCRYPTION_KEY=os.getenv('TOKEN_ENCRYPTION_KEY', ''),
        PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL', ''),
        GOOGLE_CLIENT_SECRETS=str(client_secrets),
        TEACHER_DOMAIN=os.getenv('TEACHER_DOMAIN', '').lower(),
        TEACHER_EMAILS=os.getenv('TEACHER_EMAILS', ''), STUDENT_DOMAINS=os.getenv('STUDENT_DOMAINS', ''),
        DATABASE=os.getenv('DATABASE', str(Path(app.instance_path) / 'private.sqlite3')),
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'true').lower() == 'true',
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        MAX_CONTENT_LENGTH=32*1024, SESSION_COOKIE_NAME='trasladar_session',
        PRIVACY_CONTROLLER=os.getenv('PRIVACY_CONTROLLER', ''), PRIVACY_CONTACT=os.getenv('PRIVACY_CONTACT', ''),
        PRIVACY_LEGAL_BASIS=os.getenv('PRIVACY_LEGAL_BASIS', ''), PRIVACY_RETENTION=os.getenv('PRIVACY_RETENTION', ''),
        PRIVACY_PROVIDERS=os.getenv('PRIVACY_PROVIDERS', ''))
    if config:
        app.config.update(config)
    if len(app.config['SECRET_KEY']) < 32 or app.config['SECRET_KEY'] == 'trasladar_notas_secret_key_fixed':
        raise RuntimeError('Configura SECRET_KEY aleatoria de al menos 32 caracteres.')
    base = app.config['PUBLIC_BASE_URL'].rstrip('/')
    parts = urlsplit(base)
    if parts.scheme != 'https' or not parts.netloc or parts.path or parts.query or parts.fragment or parts.username:
        raise RuntimeError('PUBLIC_BASE_URL debe ser el origen HTTPS público, sin ruta.')
    emails = {s.strip().lower() for s in app.config['TEACHER_EMAILS'].split(',') if s.strip()}
    domains = {s.strip().lower() for s in app.config['STUDENT_DOMAINS'].split(',') if s.strip()}
    if not emails or not domains or not app.config['TEACHER_DOMAIN']:
        raise RuntimeError('Configura el dominio, docentes autorizados y dominios del alumnado.')
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    store = Store(app.config['DATABASE'], app.config['TOKEN_ENCRYPTION_KEY'])
    app.extensions['store'] = store
    callback = base + '/oauth2callback'

    def flow(**kwargs):
        return Flow.from_client_secrets_file(app.config['GOOGLE_CLIENT_SECRETS'], scopes=SCOPES, redirect_uri=callback, **kwargs)

    def service():
        creds = Credentials.from_authorized_user_info(g.identity['credentials'])
        proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
        http = httplib2.Http(timeout=60, proxy_info=httplib2.proxy_info_from_url(proxy, method='https', noproxy='') if proxy else None)
        return build('drive', 'v3', http=google_auth_httplib2.AuthorizedHttp(creds, http=http), cache_discovery=False)

    @app.before_request
    def security():
        store.purge()
        g.identity = store.session(session.get('sid'))
        if g.identity and 'oauth' not in g.identity and g.identity.get('email') not in emails:
            store.logout(session['sid'])
            session.clear()
            g.identity = None
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
            if not hmac.compare_digest(token.encode(), session['csrf'].encode()):
                abort(403)
            if request.headers.get('Origin') and request.headers['Origin'] != base:
                abort(403)
        if request.path in ('/generate', '/notify') and (not g.identity or 'oauth' in g.identity):
            abort(401)

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            'Strict-Transport-Security': 'max-age=31536000'})
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(409)
    @app.errorhandler(413)
    def rejected(error):
        return jsonify(error='Solicitud rechazada. Revisa los datos o vuelve a iniciar sesión.'), error.code

    @app.route('/')
    def index():
        return render_template('index.html', authenticated=bool(g.identity and 'oauth' not in g.identity), csrf=session['csrf'])

    @app.route('/authorize')
    def authorize():
        if session.get('sid'):
            store.logout(session['sid'])
        session.clear()
        nonce = secrets.token_urlsafe(32)
        oauth = flow(autogenerate_code_verifier=True)
        url, state = oauth.authorization_url(access_type='online', prompt='select_account',
            include_granted_scopes='false', hd=app.config['TEACHER_DOMAIN'], nonce=nonce)
        session['sid'] = store.create_session({'oauth': {'state': state, 'nonce': nonce, 'verifier': oauth.code_verifier}}, 600)
        return redirect(url)

    @app.route('/oauth2callback')
    def oauth2callback():
        pending = (g.identity or {}).get('oauth')
        old_sid = session.get('sid')
        if not pending or not hmac.compare_digest(request.args.get('state', '').encode(), pending['state'].encode()):
            abort(403)
        store.logout(old_sid)
        session.clear()
        try:
            oauth = flow(state=pending['state'], code_verifier=pending['verifier'])
            oauth.fetch_token(authorization_response=callback + '?' + request.query_string.decode('ascii'))
            claims = id_token.verify_oauth2_token(oauth.credentials.id_token, Request(), oauth.client_config['client_id'])
            email = claims.get('email', '').lower()
            if (claims.get('email_verified') is not True or not claims.get('sub') or
                claims.get('hd') != app.config['TEACHER_DOMAIN'] or email not in emails or
                email.rsplit('@', 1)[-1] != app.config['TEACHER_DOMAIN'] or claims.get('nonce') != pending['nonce']):
                abort(403)
            credentials = json.loads(oauth.credentials.to_json())
            credentials['refresh_token'] = ''  # Online access only; no persistent grant retained.
            session['sid'] = store.create_session({'email': email, 'sub': claims['sub'], 'credentials': credentials}, 3600)
            session['csrf'] = secrets.token_urlsafe(32)
        except Exception:
            # OAuth exceptions can contain authorization codes or token responses.
            return jsonify(error='No se ha podido verificar una cuenta docente autorizada.'), 403
        return redirect(url_for('index'))

    @app.post('/generate')
    def generate():
        config = request.form.to_dict()
        if config.get('reviewed_source') != 'yes':
            return jsonify(error='Confirma que has revisado cabeceras, columnas, comentarios y destinatarios.'), 400
        job = None
        payload = {'items': []}
        try:
            transfer = TransferGrades(service())
            source = transfer.download(config.get('nombre_excel_notas', ''), config.get('extension') == 'Google Sheet')
            template = None
            if config.get('plantilla_cabecera', '').strip():
                template = transfer.download(config['plantilla_cabecera'].strip(),
                    config.get('extension_cabecera') == 'Google Sheet')
            items = transfer.copy_grades(source, config, domains, template)
            job = store.create_job(session['sid'])
            target_path = config.get('target_folder_path', '')
            target_folder = transfer.resolve_folder_path(target_path)
            payload['folder_id'] = transfer.new_folder(job, target_folder)
            store.save_job(job, payload, 'generating')
            for item in items:
                student_folder = transfer.new_student_folder(item['name'], payload['folder_id'])
                file_id = transfer.upload(item, student_folder, config.get('extension') == 'Google Sheet')
                payload['items'].append({'name': item['name'], 'email': item['email'],
                    'folder_id': student_folder, 'file_id': file_id, 'status': 'pending'})
                store.save_job(job, payload, 'generating')
                transfer.assert_private(file_id)
            store.save_job(job, payload, 'ready')
            return jsonify(batch_id=job, items=payload['items'])
        except InputError as error:
            message = str(error)
        except Exception:
            message = 'No se ha completado la generación. Revisa la cuenta, el archivo y la carpeta del lote en Drive.'
        if job:
            store.save_job(job, payload, 'failed')
        return jsonify(error=message, batch_id=job), 400

    @app.post('/notify')
    def notify():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or body.get('confirmed') is not True or set(body) != {'batch_id', 'confirmed'} or not isinstance(body.get('batch_id'), str):
            abort(400)
        job = body['batch_id']
        payload = store.job(job, session['sid'])
        if not payload:
            abort(403)
        if not store.claim(job, session['sid']):
            abort(409)
        payload.pop('state')
        try:
            transfer = TransferGrades(service())
            transfer.assert_private(payload['folder_id'])
            # Validate the complete batch before sending the first notification.
            for item in payload['items']:
                if item['email'].rsplit('@', 1)[-1] not in domains:
                    raise InputError('El dominio del destinatario ya no está autorizado.')
                transfer.assert_private(item['folder_id'], item['email'])
                transfer.assert_private(item['file_id'])
            for item in payload['items']:
                transfer.share(item)
                item['status'] = 'shared'
                store.save_job(job, payload, 'sharing')
            store.save_job(job, payload, 'done')
            return jsonify(status='success')
        except Exception:
            store.save_job(job, payload, 'review_required')
            return jsonify(error='El reparto puede ser parcial. Revisa los permisos en Drive; este lote no se reenvía automáticamente.', items=payload['items']), 409

    @app.post('/logout')
    def logout():
        if session.get('sid'):
            store.logout(session['sid'])
        session.clear()
        return redirect(url_for('index'))

    @app.route('/privacidad')
    def privacy():
        return render_template('privacidad.html')

    @app.cli.command('purge-expired')
    def purge_expired():
        """Erase expired technical sessions/batches (never Drive documents)."""
        store.purge()
        click.echo('Sesiones y lotes técnicos caducados eliminados. Drive no se ha modificado.')

    @app.cli.command('revoke-sessions')
    def revoke_sessions():
        """Revoke all local sessions and batches; leave Drive unchanged."""
        with store.connect() as db:
            db.execute('DELETE FROM jobs')
            db.execute('DELETE FROM sessions')
        click.echo('Todas las sesiones y lotes técnicos revocados. Drive no se ha modificado.')

    return app

if __name__ == '__main__':
    create_app().run(port=5000, debug=False)
