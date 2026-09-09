import os
import json
import flask
import google_auth_httplib2
import httplib2
from flask import Flask, request, redirect, url_for, session, render_template, jsonify
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from logic import TransferGrades

app = Flask(__name__)
app.secret_key = 'trasladar_notas_secret_key_fixed'

@app.route('/assets/<path:path>')
def send_assets(path):
    return flask.send_from_directory('assets', path)

# Path to your oauth_credentials.json from Google Cloud Console
CLIENT_SECRETS_FILE = "oauth_credentials.json"
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

def get_google_drive_service(credentials):
    # PyDrive2 compatibility shims using google-auth-httplib2
    if not hasattr(Credentials, 'access_token_expired'):
        Credentials.access_token_expired = property(lambda self: self.expired)
    
    if not hasattr(Credentials, 'authorize'):
        # This shim correctly wraps the http object with modern credentials
        def authorize_shim(self, http):
            return google_auth_httplib2.AuthorizedHttp(self, http)
        Credentials.authorize = authorize_shim
        
    if not hasattr(Credentials, 'refresh_token_expired'):
        Credentials.refresh_token_expired = False
    
    gauth = GoogleAuth()

    # PythonAnywhere free accounts require outbound HTTP(S) traffic to use
    # their proxy.  PyDrive2 creates its own httplib2 transport for each
    # thread, so configuring requests (or a one-off transport) is not enough.
    # Build every PyDrive2 transport with the proxy explicitly and do not let
    # NO_PROXY accidentally bypass it for googleapis.com.
    proxy_url = os.environ.get('https_proxy') or os.environ.get('HTTPS_PROXY')

    def build_http_transport():
        if proxy_url:
            proxy_info = httplib2.proxy_info_from_url(
                proxy_url,
                method='https',
                noproxy=''
            )
            http = httplib2.Http(proxy_info=proxy_info, timeout=60)
        else:
            http = httplib2.Http(timeout=60)

        # Google Drive uses 308 for resumable uploads, not as a permanent
        # redirect.  Keep the same behaviour as PyDrive2's default transport.
        try:
            http.redirect_codes = http.redirect_codes - {308}
        except AttributeError:
            pass
        return http

    gauth._build_http = build_http_transport
    gauth.credentials = credentials
    return GoogleDrive(gauth)

@app.route('/')
def index():
    if 'credentials' not in session:
        return render_template('index.html', authenticated=False)
    return render_template('index.html', authenticated=True)

@app.route('/authorize')
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = url_for('oauth2callback', _external=True, _scheme='https')
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true')
    session['state'] = state
    session['code_verifier'] = flow.code_verifier
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    if 'state' not in session:
        return redirect(url_for('authorize'))
    
    state = session['state']
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = url_for('oauth2callback', _external=True, _scheme='https')
    flow.code_verifier = session.get('code_verifier')

    authorization_response = flask.request.url.replace('http://', 'https://')
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    return redirect(url_for('index'))

@app.route('/generate', methods=['POST'])
def generate():
    if 'credentials' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    creds = Credentials(**session['credentials'])
    drive = get_google_drive_service(creds)
    transfer_logic = TransferGrades(drive, creds)

    config = {
        'nombre_excel_notas': request.form.get('nombre_excel_notas'),
        'nombre_hoja': request.form.get('nombre_hoja'),
        'numero_cabecera': int(request.form.get('numero_cabecera', 0)),
        'letra_columna_nombre': request.form.get('letra_columna_nombre'),
        'letra_columna_correo': request.form.get('letra_columna_correo'),
        'plantilla_cabecera': request.form.get('plantilla_cabecera'),
        'extension_cabecera': request.form.get('extension_cabecera'),
        'nombre_otras_hoja': request.form.get('lista_otras_hoja', '').split(','),
        'path_target': 'output',
        'convert_to_sheet': request.form.get('extension') == 'Google Sheet'
    }

    try:
        # 0. Cleanup previous run
        transfer_logic.cleanup_local_files(config['path_target'])

        # 1. Search for the main file
        local_file, file_id = transfer_logic.search_file(
            config['nombre_excel_notas'], 
            request.form.get('extension') == 'Google Sheet'
        )
        
        if not local_file:
            return jsonify({'error': 'Main file not found'}), 404

        # 2. Process and create local folders/files
        results = transfer_logic.copy_grades(config)

        # 3. Upload to Drive (Step 1 complete)
        target_folder_id = request.form.get('target_folder_id', 'root')
        uploaded_items = transfer_logic.upload_folders(results, target_folder_id, convert=config['convert_to_sheet'])

        return jsonify({'status': 'success', 'items': uploaded_items})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/notify', methods=['POST'])
def notify():
    if 'credentials' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    creds = Credentials(**session['credentials'])
    drive = get_google_drive_service(creds)
    transfer_logic = TransferGrades(drive, creds)

    try:
        items = request.json.get('items', [])
        if not items:
            return jsonify({'error': 'No items to notify'}), 400
        
        results = transfer_logic.share_with_students(items)
        return jsonify({'status': 'success', 'results': results})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get("PORT", 80)))
