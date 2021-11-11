DIGITALIZACIÓN EDUCATIVA
==================
# Herramienta para trasladar la evaluación al alumnado y fomentar la retroalimentación

  > Accesible desde [aquí](https://colab.research.google.com/github/anderfrago/TrasladarNotasAlumnos/blob/main/2021_CompartirCompetenciasClave.ipynb)

 ### Colab que permite trasladar automáticamente las notas de la evolución a lo largo del curso, de manera individual, al alumnado a partir de un Sheet alojado en Google Drive (GDrive).
 ### Una vez finalizado el proceso, el alumnado recibe un correo. El correo da acceso a la carpeta compartida donde se ubica la hoja de evaluación.
 En caso de establecer *notas (comentarios) en las casillas* dentro del Sheet a compartir, el alumnado lo recibirá como comentarios con opción de respuesta o resolución. **Respondiendo a los comentarios se fomenta la retroalimentación del proceso de evaluación**. Al responder a los comentarios el docente recibe la notificación vía correo.
  
  > En caso de querer trasladar más de un documento es necesario ejecutar la celda de reinicio de máquina

 ###### INFORMACIÓN REQUERIDA
 
1. **El nombre del archivo con las notas.** 
2. **Se requiere la ruta al archivo dentro de GDrive**, partiendo de *Mi Unidad*. 
3. **Se requiere la letra de la columna en la que aparecen los nombres del alumando.**
4. **Se requiere la letra de la columna en la que aparecen los correos del alumnado.**
5. **Se requiere el número de filas reservadas para la cabecera.** *Línea donde comienzan los alumnos-1.*
 
 ###### OPCIONES
 

 1. **Nombre de hoja.** Permite establecer el nombre de la hoja a trasladar, de no definirse se trasladará la primera hoja 
 2. **Google Sheets y Excel.** Permite trasladar tanto hojas GSheet como Excel. *El alumnado siempre recibe un documento xlsx*
 3. **Cabecera avanzada.** En caso de utilizar columnas agrupadas, podemos trasladar este tipo de cabecera avanzada mediante una plantilla. Gracias a esta plantilla se compia la cabecera respetando las colummnas colapsadas. La plantilla consiste en el mismo documento GSheet pero sin las líneas correspondientes al alumando.

 
 
