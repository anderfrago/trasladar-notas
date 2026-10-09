# Trasladar notas

Aplicación Flask para generar documentos individuales de evaluación a partir de una hoja de Google Drive y entregarlos tras revisión docente.

**Antes de actualizar:** lee [la guía de privacidad, funcionamiento y despliegue](docs/PRIVACIDAD_Y_ACTUALIZACION.md). Incluye el diagrama, la configuración necesaria, los cambios de comportamiento y los requisitos pendientes del centro.

El acceso se permite a cuentas Google Workspace verificadas del dominio corporativo configurado en `TEACHER_DOMAIN`, sin lista individual de correos. En Cuatrovientos, `cuatrovientos.org` corresponde al personal; el centro debe autorizar este alcance de uso. Cada persona conserva únicamente los permisos de su propia cuenta de Drive. Se generan archivos nuevos en una carpeta privada y se comparte cada documento con su destinatario en modo lectura. El servidor vincula cada lote a la sesión que lo creó. Se requiere revisión humana de las cabeceras, todas las columnas, comentarios y destinatarios.

Las plantillas y pestañas adicionales están deshabilitadas; no se copian fórmulas ni se reutilizan carpetas. Las calificaciones de Drive y las descargas requieren una política de conservación del centro. El borrado de sesiones no elimina esos documentos.

Instalación: `pip install -r requirements.txt`, completar `.env` a partir de `.env.example` y configurar WSGI con `from wsgi import application`. No ejecutar la versión histórica del cuaderno ni servir el `index.html` de la raíz como aplicación.

Pruebas sin Google real: `pip install -r requirements-dev.txt` y `python -m pytest tests -q`.
