const form = document.getElementById('transferForm');
const statusBox = document.getElementById('status');
const csrf = document.querySelector('meta[name="csrf-token"]').content;
let batchId = null;
function show(message, ok = false) {
    statusBox.style.display = 'block';
    statusBox.className = `status-card status-${ok ? 'success' : 'error'}`;
    statusBox.textContent = message;
}
async function post(url, body, json = false) {
    const headers = {'X-CSRF-Token': csrf};
    if (json) headers['Content-Type'] = 'application/json';
    const response = await fetch(url, {method: 'POST', headers, body: json ? JSON.stringify(body) : body});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'No se ha completado la operación.');
    return result;
}
if (form) {
    const notify = document.getElementById('notifyBtn');
    const submit = document.getElementById('submitBtn');
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        submit.disabled = true;
        try {
            const result = await post('/generate', new FormData(form));
            batchId = result.batch_id;
            const list = document.getElementById('studentList');
            list.replaceChildren();
            for (const item of result.items) {
                const row = document.createElement('p');
                const link = document.createElement('a');
                link.textContent = 'Abrir y revisar';
                link.href = 'https://drive.google.com/file/d/' + encodeURIComponent(item.file_id) + '/view';
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                row.append(document.createTextNode(`${item.name} — ${item.email} `), link);
                list.append(row);
            }
            document.getElementById('step1').style.display = 'none';
            document.getElementById('step2').style.display = 'block';
            notify.disabled = false;
        } catch (error) { show(error.message); }
        finally { submit.disabled = false; }
    });
    notify.addEventListener('click', async () => {
        if (!confirm('¿Has revisado cada archivo y confirmado que corresponde a su destinatario? Google compartirá los archivos en modo lectura y enviará las notificaciones.')) return;
        notify.disabled = true;
        try {
            await post('/notify', {batch_id: batchId, confirmed: true}, true);
            show('Carpetas individuales compartidas en modo lectura. El lote permanece privado.', true);
        } catch (error) {
            show(error.message + ' Si se interrumpió la conexión, revisa Drive antes de generar otro lote.');
        }
    });
    document.getElementById('backBtn').addEventListener('click', () => {
        batchId = null;
        document.getElementById('step1').style.display = 'block';
        document.getElementById('step2').style.display = 'none';
        show('Las copias ya generadas siguen en Drive. Revisa y elimina las que no necesites.');
    });
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        await fetch('/logout', {method: 'POST', headers: {'X-CSRF-Token': csrf}});
        location.href = '/';
    });
}
