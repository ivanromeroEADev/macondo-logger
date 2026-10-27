# Macondo Logger

<img src="macondo_logo.jpg" width="110" align="right" alt="Mariposa amarilla, logo de Macondo Logger">

Macondo Logger es una app para reportar bugs en JaaS sin pelear con el formulario. Sirve para cualquier proyecto: Skate, Madden, The Sims o el tuyo.

Reportar un bug bien hecho toma tiempo. Hay que llenar todos los campos obligatorios del proyecto, escribir los pasos para reproducirlo con el formato que espera el equipo y cuidar que el summary siga la convención. Muchas veces el bug se entiende en una frase, pero dejarlo listo toma media hora.

Con Macondo tú describes el bug con tus palabras. La app lee de JaaS los campos que tu proyecto exige, y una IA escribe el summary y la descripción con la plantilla de QA de Skate, adaptada al estilo de tu proyecto. Antes de enviar, tú lo revisas y lo corriges. Nada se envía sin que lo confirmes.

Además aprende. Cada vez que corriges un borrador, guarda esa corrección y la usa como ejemplo la próxima vez. Más abajo explico cómo funciona y dónde queda guardado lo que aprende.

El nombre viene de *Cien años de soledad*. De ahí la mariposa amarilla.

---

## Qué necesitas

**Windows 10 u 11** y **Python 3.11 o más nuevo** (yo la uso con Python 3.14). Para saber si ya tienes Python, abre una terminal (tecla Windows, escribe `cmd`, Enter) y escribe `python --version`. Si responde algo como `Python 3.12.4`, ya está.

**Acceso a JaaS** con permiso para crear tickets en tu proyecto, y **tu propio Personal Access Token (PAT)**. Cada persona usa el suyo, así cada ticket queda creado a su nombre.

Para crearlo: entra a [jaas.ea.com](https://jaas.ea.com), haz clic en tu foto de perfil y ve a **Profile → Personal Access Tokens → Create token**. Ponle un nombre como "Macondo" y copia el token apenas aparezca, porque JaaS no te lo vuelve a mostrar.

**Una API key de Groq.** Groq es el servicio que ejecuta el modelo de IA que escribe los borradores. Se crea en [console.groq.com/keys](https://console.groq.com/keys). El plan gratuito alcanza para reportar bugs a diario.

> **Sobre la información que sale de EA:** para escribir el borrador, la app le envía a Groq tu descripción del bug y algunos tickets recientes de tu proyecto, que usa como ejemplo de formato. Antes de usarla en tu equipo, confirma con tu lead que eso está permitido para tu proyecto.

---

## Instalación

### 1. Instala Python (si no lo tienes)

Descárgalo de [python.org/downloads](https://www.python.org/downloads/) y ejecuta el instalador.

En la primera pantalla hay una casilla que dice **"Add python.exe to PATH"**. **Márcala.** Es el error más común: si no la marcas, Windows no encuentra Python y nada de lo que sigue funciona.

Cuando termine, cierra las terminales que tengas abiertas y abre una nueva.

### 2. Descarga el repositorio

Desde la página del repo, **Code → Download ZIP**, y descomprímelo donde quieras, por ejemplo en `Documentos\macondo-logger`. Si usas git, también puedes clonarlo.

No tienes que configurar nada más. El repo ya trae el `config.json` con la dirección de JaaS.

### 3. Abre la app

Doble clic en **`run.bat`**.

La primera vez se demora unos minutos porque instala lo que la app necesita. Las siguientes abre en segundos. Cuando esté lista se abre sola en tu navegador. Si no se abre, entra a [http://localhost:8501](http://localhost:8501).

La ventana negra tiene que quedarse abierta mientras usas la app. Cuando termines, ciérrala.

Si prefieres hacerlo a mano, desde la carpeta del proyecto:

```
python -m pip install -r requirements.txt
python -m streamlit run macondo_app.py
```

### 4. La primera vez

1. **Pega tu Groq API key** y dale *Guardar Groq API Key*. Solo se pide una vez por computador.
2. **Pega tu PAT de JaaS**, deja marcada *Recordar en este equipo* y dale *Conectar*.

Las dos claves se guardan cifradas en el **Administrador de credenciales de Windows**, bajo el nombre `macondo-logger`. No quedan en ningún archivo de texto. Si ya usabas una versión anterior de Macondo, la app encuentra tus claves viejas y no te las vuelve a pedir.

### Cerrar sesión

En la barra lateral izquierda siempre ves con qué usuario estás conectado y a qué JaaS. Ahí está el botón **Cerrar sesión**: borra tu token de este computador y vuelve a la pantalla de conexión, lista para que entre otra persona o para pegar un token nuevo.

Si marcas **Olvidar también la Groq API Key**, se borra también la key de Groq. Eso es útil si el computador lo usa otra persona. Lo que Macondo aprendió de tus proyectos no se borra al cerrar sesión.

---

## Cómo se usa

1. **Elige tu proyecto.** Aparecen solo los proyectos donde puedes crear tickets, con los que usaste hace poco de primeros. Si no ves el tuyo, escribe la clave a mano.

2. **Revisa el Issue Type.** Por defecto la app elige **Bug**. Si necesitas otro tipo, cámbialo en la lista y el formulario se recarga con los campos de ese tipo.

3. **Llena los campos.** La app trae de JaaS **todos los campos obligatorios** que tu proyecto exige para ese Issue Type, marcados con asterisco, y no te deja generar el bug hasta que estén llenos. Funciona con cualquier tipo de campo: listas, listas en cascada, componentes, versiones, usuarios, fechas, números y etiquetas. Los opcionales que no son comunes quedan en *Otros campos*, para no llenarte la pantalla.

   *Feature* es opcional y no es un campo de JaaS: va en la nota de la descripción, como en Skate.

4. **Describe el bug** como se lo contarías a un compañero: qué pasa, dónde y qué esperabas. Puedes adjuntar logs y videos, o pegar un screenshot con Ctrl+V.

5. **Dale "Generar con IA".** En unos segundos tienes el summary y la descripción.

6. **Revisa y corrige.** Todo es editable. Lo que cambies aquí es lo que la app aprende.

7. **"Confirmar y enviar".** El ticket se crea, se suben los adjuntos y te queda el link.

Si JaaS rechaza algún campo **opcional**, la app lo quita, crea el ticket igual y te dice cuál campo no se pudo aplicar. Los obligatorios nunca se quitan.

---

## La plantilla y cómo aprende de cada proyecto

Todos los bugs salen de la **plantilla de QA de Skate**: un párrafo corto con qué falla, Repro Rate, Repro Steps que empiezan con *Boot* y terminan con *Notice that…*, Player Impact y una nota con Pillar y Feature. La mayoría de proyectos de EA usan algo muy parecido, así que es la base para todos.

Encima de esa base, la app se adapta a cada proyecto. Lo que hace se llama *few-shot learning*: no entrena un modelo propio, sino que cada vez que pide un borrador le pasa a la IA ejemplos reales de cómo se escribe en ese proyecto, y la IA ajusta la plantilla a esos ejemplos. Son tres capas, de menor a mayor peso:

1. **La plantilla de Skate.** Siempre está. Define la estructura por defecto.
2. **Los tickets reales del proyecto.** Cada vez que abres un proyecto, la app busca en JaaS los tickets recientes **tuyos** de ese Issue Type en ese proyecto. Si no tienes, busca los del equipo. Toma hasta 3 descripciones con estructura de verdad y hasta 6 summaries. Si tu proyecto llama distinto a una sección o agrega una que Skate no tiene, la IA lo copia. Estos ejemplos **no se guardan en disco**: se leen cada vez que abres el proyecto, así que si el equipo cambia su plantilla en JaaS, Macondo lo nota.
3. **Tus correcciones.** Cuando editas un borrador antes de enviarlo, la app guarda tu versión corregida y la usa en los siguientes borradores de ese proyecto. Es lo que más pesa.

**El summary** sigue la convención de cada proyecto. Si el proyecto tiene los campos *Pillar* y *Game Spine*, como Skate, la app arma el prefijo `Pillar - Game Spine - …` con lo que elegiste en el formulario. Si no los tiene, la IA copia el formato completo de los summaries de ese proyecto, prefijo incluido.

### Dónde se guarda lo que aprende

Todo queda en tu computador, en:

```
%APPDATA%\MacondoLogger\
```

Pega esa ruta en la barra de direcciones del Explorador de archivos para llegar directo. Normalmente es `C:\Users\tu_usuario\AppData\Roaming\MacondoLogger\`.

Ahí hay dos archivos por proyecto, con la clave del proyecto en el nombre:

| Archivo | Qué tiene |
|---|---|
| `buglogger_examples_SK8.json` | Tus correcciones en SK8: lo que escribiste originalmente, y el summary y la descripción ya corregidos. En cada borrador se usan las 3 más recientes. |
| `buglogger_stats_SK8.json` | Las métricas de ese proyecto: borradores generados, enviados, corregidos y qué tanto se parecía el borrador a lo que enviaste. |

Cada proyecto aprende por separado. Lo que corriges en Skate no afecta los borradores de Madden.

Lo aprendido **es de cada computador**, no del equipo. Si cinco testers usan Macondo en el mismo proyecto, cada uno enseña al suyo. Igual, todos parten de los mismos tickets reales del proyecto.

**Para empezar de cero en un proyecto,** borra su `buglogger_examples_<PROYECTO>.json`. **Para llevarte lo aprendido a otro computador,** copia la carpeta `MacondoLogger` completa al mismo lugar en el otro equipo.

### Cómo saber si está mejorando

En el formulario, debajo del nombre del proyecto, aparece la **accuracy**: el porcentaje de tickets que enviaste sin tener que reescribir el borrador. Si con el tiempo sube, Macondo está aprendiendo bien el estilo del proyecto. Justo arriba verás también con qué está escribiendo, por ejemplo: *"Escribe con: plantilla Skate + 3 ticket(s) reales tuyos + 2 corrección(es) tuyas"*.

### Dónde está en el código

Todo el aprendizaje vive en `core.py`, en la sección marcada como `COMPONENTE DE APRENDIZAJE`:

| Función | Qué hace |
|---|---|
| `SKATE_TEMPLATE` | La plantilla base de Skate |
| `fetch_project_style()` / `project_style_block()` | Traen de JaaS los tickets reales del proyecto |
| `save_example()` / `load_examples()` / `recent_examples_block()` | Guardan y leen tus correcciones |
| `generate_description()` / `generate_summary()` | Arman el prompt con las tres capas y llaman a Groq |
| `record_generation()` / `record_submission()` / `accuracy_report()` | Las métricas de accuracy |

La decisión de guardar una corrección se toma en `bug_logger_ui.py`, en `_stage_preview()`, cuando le das *Confirmar y enviar*. Solo se guarda si editaste algo.

---

## Si algo sale mal

**"python no se reconoce como un comando".** Python no quedó en el PATH. Reinstálalo marcando *Add python.exe to PATH*. `run.bat` también prueba con `py`, que a veces funciona aunque `python` no.

**"streamlit no se reconoce como un comando".** Usa `python -m streamlit run macondo_app.py`. No depende del PATH.

**"Token inválido".** Revisa que copiaste el PAT completo y que no haya expirado. Si lo acabas de crear y sigue fallando, crea otro.

**Quiero cambiar de token o de usuario.** Usa *Cerrar sesión* en la barra lateral y pega el nuevo.

**Mi proyecto no aparece.** Escribe la clave a mano en *¿No ves tu proyecto?*. Si dice que no puede leer los campos, probablemente no tienes permiso para crear tickets en ese proyecto. Pídeselo a tu lead.

**Aparece en rojo "Este proyecto exige campos que la app todavía no sabe llenar".** Tu proyecto tiene un campo obligatorio de un tipo poco común. Crea ese ticket desde JaaS y avísale a quien mantiene Macondo, con el nombre del campo, para agregarlo.

**JaaS rechaza el ticket.** La app muestra el error con el nombre del campo. Casi siempre es un valor que el proyecto no acepta en ese momento, por ejemplo una versión cerrada. Corrígelo en el formulario y vuelve a intentar.

**Error de Groq que menciona el modelo (`model_decommissioned` o `model_not_found`).** Groq retira modelos de vez en cuando. Busca uno vigente en [console.groq.com/docs/models](https://console.groq.com/docs/models) y cámbialo en `groq_model` dentro de `config.json`.

**El puerto 8501 está ocupado.** Ya tienes otra ventana de Macondo abierta. Usa esa o ciérrala.

---

## Para quien mantiene el repo: `config.json`

El repo trae un `config.json` con lo que es propio de EA. No hace falta tocarlo para usar la app, solo para ajustarla:

| Clave | Para qué sirve |
|---|---|
| `jira_url` / `browse_url` | La API de JaaS (`api.jaas.ea.com`) y la dirección para abrir tickets en el navegador (`jaas.ea.com`). |
| `default_issue_type` | El Issue Type que se elige al abrir un proyecto. Por defecto, `Bug`. |
| `branches` | Branches sugeridas **por proyecto**, en una lista desplegable. Skate trae las `dingo-*`. Para agregar otro proyecto: `"MAD": ["main", "release"]`. Si un proyecto no está, la branch se escribe a mano. |
| `bug_types` | Opciones de *Bug Type* cuando el proyecto lo tiene como texto libre. |
| `test_projects` | Proyectos de pruebas. Al enviar a cualquier otro, la app muestra una advertencia de "proyecto real". |
| `fallback_projects` | Proyectos que se muestran si JaaS no deja listar los del usuario. |
| `field_names` | Opcional. Cómo se llaman los campos que la app usa como contexto para la IA (Pillar, Severity, Repro Rate…). Ya vienen los de Skate; solo cámbialo si un proyecto los llama distinto. |
| `groq_model` | El modelo de Groq que escribe los borradores. |

### Hacer un .exe

Para repartir la app a gente sin Python, doble clic en `build_exe.bat`. En unos minutos queda `dist\MacondoLogger.exe`, con el `config.json` adentro. Cada persona pega su propia Groq key y su propio PAT la primera vez.

Windows puede mostrar *"Windows protegió su PC"* porque el `.exe` no está firmado. Se pasa con *Más información → Ejecutar de todas formas*. Para repartirlo a mucha gente, lo ideal es firmarlo con el certificado de la empresa.

### Pruebas

Simulan JaaS y Groq, así que corren sin conexión y sin tokens:

```
python -m pip install pytest
python -m pytest -q
```

Cubren el Issue Type por defecto y el cambio de tipo, que todos los obligatorios lleguen al formulario (incluidas listas en cascada, componentes, versiones y usuarios), el formato de cada campo al enviar, el reintento cuando JaaS rechaza un campo opcional, las tres capas del aprendizaje y la métrica de accuracy.

### Qué hay en cada archivo

```
macondo_app.py        la app: junta el tema, la conexión y la pantalla del logger
bug_logger_ui.py      las pantallas: proyecto, formulario, vista previa y listo
core.py               JaaS, Groq, plantilla, aprendizaje y métricas
macondo_login.py      la conexión, el cierre de sesión y el guardado cifrado de claves
macondo_theme.py      colores, tipografía y la cabecera con la mariposa
config.json           configuración de EA
run.bat               abre la app con doble clic
build_exe.bat         compila el .exe
MacondoLogger.spec    receta de PyInstaller para el .exe
launcher_macondo.py   punto de entrada del .exe
_launcher_base.py     arranca Streamlit dentro del .exe
tests/                pruebas automáticas
```

---

Creado por Iván Romero (QV, Skate · Bogotá).
