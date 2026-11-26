# Memoria_PaaS — Caso 3: Docker Compose con IA en Azure App Service

> Estado: el proyecto está preparado y probado localmente. No se ha creado un despliegue real en una suscripción Azure desde este entorno. Las URLs reales, nombres de recursos y capturas deben completarse al ejecutar los comandos desde una cuenta propia.

## 1. Descripción del despliegue elegido

Se implementa el caso 3 de la práctica: una aplicación Docker Compose multicontenedor desplegada en Azure App Service para Linux. El contenedor `chat` proporciona una interfaz web Flask, identifica chats por la cookie firmada del navegador, permite editar títulos y persiste conversaciones y mensajes en SQLite. Al enviar un mensaje, `chat` reenvía el historial al contenedor `ia`. Este segundo contenedor valida la petición, consulta Gemini y devuelve el texto generado.

Azure App Service expone una única URL pública correspondiente al puerto 8080 de `chat`. El contenedor `ia` no publica puertos al exterior y es alcanzable desde `chat` mediante el nombre interno `ia:8000`. Las imágenes se almacenan en ACR y se descargan desde App Service. La clave Gemini se configura como App setting, nunca en Compose ni en una imagen. Para persistencia, se habilita el almacenamiento de App Service y se monta una carpeta del directorio `${WEBAPP_STORAGE_HOME}` en `/data`, donde se guarda `chats.db`.

Los recursos usados son un grupo de recursos, Azure Container Registry, un plan Linux App Service B1 y una aplicación web Linux con configuración Docker Compose. App Service administra la plataforma y los contenedores; el usuario administra las imágenes, secretos, configuración y datos. El despliegue se realiza por Azure CLI, dejando el portal solo para comprobar recursos y aplicaciones.

## 2. Arquitectura y comunicación

```text
Usuario
  |
  | HTTPS
  v
Azure App Service, URL única
  |
  +-- chat :8080 (Flask + SQLite)
       |
       | red interna Compose, http://ia:8000
       v
     ia :8000 (Flask)
       |
       | HTTPS
       v
     API Gemini
```

La comunicación comprobada es:

1. El navegador crea o selecciona un chat.
2. `chat` guarda el mensaje del usuario en SQLite.
3. `chat` envía hasta 40 mensajes de historial a `POST http://ia:8000/v1/chat`.
4. `ia` transforma el historial al formato Gemini, añade la clave mediante cabecera y espera la respuesta.
5. `ia` devuelve JSON con `reply`.
6. `chat` guarda la respuesta como mensaje `model` y la muestra al navegador.

## 3. Contenedores e imágenes

| Imagen | Base Docker Hub | Dockerfile | Función |
|---|---|---|---|
| `<ACR>.azurecr.io/chat:v1` | `python:3.12-slim` | `chat_service/Dockerfile` | Web, rutas API y SQLite |
| `<ACR>.azurecr.io/ia:v1` | `python:3.12-slim` | `ai_service/Dockerfile` | Adaptador privado a Gemini |

Se añadieron Flask, Gunicorn y Requests a las dependencias. Gunicorn sirve cada aplicación. Se añadió validación de entradas, límites de longitud, sesiones firmadas por Flask y conexiones SQLite controladas por petición. La interfaz permite crear, renombrar y eliminar chats; se pueden renombrar con doble clic tanto desde la lista como desde el título abierto. Enter envía el mensaje y Shift+Enter inserta un salto de línea.

El Dockerfile de `chat`:

1. Parte de Python slim.
2. Instala dependencias.
3. Copia la aplicación, plantillas y recursos estáticos.
4. Expone el puerto 8080.
5. Arranca Gunicorn enlazado a `0.0.0.0:8080`.

El Dockerfile de `ia`:

1. Parte de Python slim.
2. Instala dependencias.
3. Copia `app.py`.
4. Expone el puerto 8000.
5. Arranca Gunicorn enlazado a `0.0.0.0:8000`.

No se utiliza Docker Hub para el despliegue en Azure: las imágenes finales se construyen en ACR mediante `az acr build` y el Compose solo referencia el registro privado.

## 4. Prueba local

Requisitos: Docker Engine y Docker Compose v2, y una clave Gemini válida recién creada.

1. Crea un fichero de entorno sin subirlo al repositorio:

   ```sh
   cp .env.example .env
   ```

2. Edita `.env` y sustituye las claves ficticias.

3. Construye y arranca:

   ```sh
   docker compose -f compose.local.yaml up --build -d
   docker compose -f compose.local.yaml ps
   ```

4. Abre `http://localhost:8080`.

5. Crea al menos dos chats, renombra uno con doble clic en la lista y otro desde el título de la conversación, y prueba el envío con Enter y los saltos de línea con Shift+Enter.

6. Comprueba salud y persistencia:

   ```sh
   curl -fsS http://localhost:8080/healthz
   docker compose -f compose.local.yaml restart chat
   docker compose -f compose.local.yaml logs --tail=100 chat ia
   ```

7. Conserva datos al detener:

   ```sh
   docker compose -f compose.local.yaml down
   ```

   Para borrarlos:

   ```sh
   docker compose -f compose.local.yaml down -v
   ```

El Compose local contiene `build` y un volumen nombrado. Es distinto del [compose.yaml](compose.yaml) enviado a App Service: este último solo tiene imágenes de ACR y volumen bajo `${WEBAPP_STORAGE_HOME}`.

## 5. Compose enviado a Azure

El contenido utilizado para App Service es:

```yaml
services:
  ia:
    image: REPLACE_ACR.azurecr.io/ia:v1
    environment:
      GEMINI_API_KEY:
      GEMINI_MODEL: gemini-3.1-flash-lite
    expose:
      - "8000"
    restart: unless-stopped

  chat:
    image: REPLACE_ACR.azurecr.io/chat:v1
    depends_on:
      - ia
    environment:
      AI_SERVICE_URL: http://ia:8000
      DATABASE_PATH: /data/chats.db
      FLASK_SECRET_KEY:
    ports:
      - "8080:8080"
    volumes:
      - ${WEBAPP_STORAGE_HOME}/chat:/data
    restart: unless-stopped
```

Se conserva `depends_on` con una condición de salud local, aunque App Service puede ignorarla; los dos contenedores se encuentran al mismo tiempo y `chat` maneja temporalmente el error si `ia` todavía no está listo. Los healthchecks verifican `/healthz` en ambos contenedores.

## 6. Despliegue en Azure por consola

### 6.1 Variables y acceso

Todos los nombres con paréntesis son ejemplos y deben sustituirse por valores únicos:

```sh
az login
az account set --subscription "<SUBSCRIPCIÓN>"

export LOCATION="westeurope"
export RG="rg-ics-chat-gemini"
export ACR="<ACR_UNICO>"
export PLAN="plan-ics"
export APP="<APP_UNICA>"
export SKU="B1"
```

No se debe ejecutar desde el portal: el registro, las imágenes, el plan, la aplicación y sus ajustes se crean desde CLI. El portal se utiliza solo para revisar.

### 6.2 Recursos e imágenes

```sh
az group create --name "$RG" --location "$LOCATION"

az acr create --resource-group "$RG" --name "$ACR" --sku Basic
az acr build --registry "$ACR" --image chat:v1 ./chat_service
az acr build --registry "$ACR" --image ia:v1 ./ai_service

az acr repository list --name "$ACR" --output table
```

Los últimos comandos permiten verificar que `chat` e `ia` están en ACR antes de crear la aplicación.

### 6.3 Compose definitivo

Cambia `REPLACE_ACR` en [compose.yaml](compose.yaml) por el nombre real, sin `https://` y sin secretos:

```yaml
image: <ACR_UNICO>.azurecr.io/chat:v1
image: <ACR_UNICO>.azurecr.io/ia:v1
```

No añadas `GEMINI_API_KEY` ni `FLASK_SECRET_KEY` al fichero.

### 6.4 Plan y aplicación multicontenedor

```sh
az appservice plan create \
  --name "$PLAN" --resource-group "$RG" \
  --is-linux --sku "$SKU"

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$APP" \
  --multicontainer-config-type compose \
  --multicontainer-config-file compose.yaml
```

### 6.5 Registro privado

El siguiente método usa las credenciales de administrador temporalmente. Esta práctica las presenta desde CLI; después conviene desactivar el usuario administrador y usar una identidad administrada o credenciales administradas por Azure.

```sh
az acr update --name "$ACR" --admin-enabled true
ACR_USER=$(az acr credential show --name "$ACR" --query username -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR" --query 'passwords[0].value' -o tsv)

az webapp config container set \
  --resource-group "$RG" \
  --name "$APP" \
  --container-registry-url "https://$ACR.azurecr.io" \
  --container-registry-user "$ACR_USER" \
  --container-registry-password "$ACR_PASS"

unset ACR_PASS
```

No escribas ni captures `ACR_PASS`.

### 6.6 Secretos y persistencia

Genera una clave Flask aleatoria y usa una clave Gemini nueva; no reutilices una clave expuesta:

```sh
GEMINI_KEY=$(python3 -c 'print(input())')
FLASK_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings \
    WEBSITES_ENABLE_APP_SERVICE_STORAGE=true \
    GEMINI_API_KEY="$GEMINI_KEY" \
    GEMINI_MODEL="gemini-3.1-flash-lite" \
    FLASK_SECRET_KEY="$FLASK_SECRET" \
    AI_SERVICE_URL="http://ia:8000" \
    DATABASE_PATH="/data/chats.db"

unset GEMINI_KEY FLASK_SECRET
```

El comando anterior presenta una entrada visible para `GEMINI_KEY`. Una alternativa segura es llamar `read -s GEMINI_KEY`, que oculta la entrada en terminal; no debe incluirse en la memoria real ni en capturas.

El volumen `${WEBAPP_STORAGE_HOME}/chat:/data` guarda el fichero SQLite de chat en el almacenamiento persistente administrado por App Service. Reiniciar o recrear el contenedor no elimina `/data/chats.db`.

### 6.7 Actualización y comprobación

Después de cualquier cambio en `compose.yaml`:

```sh
az webapp config container set \
  --resource-group "$RG" \
  --name "$APP" \
  --multicontainer-config-type compose \
  --multicontainer-config-file compose.yaml

az webapp restart --resource-group "$RG" --name "$APP"
```

Obtén la única URL pública:

```sh
HOST=$(az webapp show --resource-group "$RG" --name "$APP" \
  --query defaultHostName --output tsv)
printf 'https://%s\n' "$HOST"
curl -fsS "https://$HOST/healthz"
```

Configura y consulta logs:

```sh
az webapp log config \
  --resource-group "$RG" --name "$APP" \
  --docker-container-logging filesystem

az webapp log tail --resource-group "$RG" --name "$APP"
```

**URL pública real (completar tras el despliegue):** `https://<HOST_REAL>`.

No existe URL pública para `ia`. Solo `chat` está publicado por el puerto 8080; el nombre `ia` solo pertenece a la red interna de Compose.

## 7. Capturas necesarias

No se deben usar capturas simuladas ni mostrar secretos. Añadir al ZIP:

1. Registro ACR desde consola mostrando `chat:v1` e `ia:v1`.
2. Plan y aplicación creados desde CLI.
3. App Service con Compose multicontenedor activo.
4. App settings mostrando variables nombradas, ocultando el valor de Gemini.
5. Comprobación local de `docker compose ps`.
6. Interfaz con al menos dos chats y títulos editables.
7. Resultado de una conversación con Gemini.
8. Reinicio del chat y verificación de que los mensajes persisten.
9. `az webapp log tail` mostrando ambos contenedores o los eventos disponibles.
10. URL pública abierta desde el navegador.

## 8. Errores y soluciones

- **Diseño inicial erróneo:** se habían descrito Azure Container Apps, pero la práctica pide Docker Compose en Azure App Service para el caso 3. Se corrigió la arquitectura, Compose, persistencia y comandos.
- **Clave expuesta:** la clave proporcionada originalmente debe revocarse. La solución la recibe únicamente como `GEMINI_API_KEY` de App Service y no la escribe en archivos ni imágenes.
- **App Service no hace build:** se eliminó `build` del Compose desplegado. Las imágenes se crean antes con `az acr build` y solo se despliegan desde ACR.
- **Persistencia:** se habilita `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true` y se monta `${WEBAPP_STORAGE_HOME}/chat:/data`, evitando perder SQLite al reiniciar.
- **IA no accesible:** `ia` no publica puertos. `chat` usa el nombre DNS interno `ia:8000`.
- **`depends_on` limitado:** App Service puede no respetar el orden de inicio. El endpoint de chat devuelve un error controlado si la IA todavía no está disponible y permite reintentar.
- **Nombres únicos:** ACR y nombre de App Service deben ser únicos en Azure; no se deben copiar literalmente los ejemplos.
- **Límites o cuota de Gemini:** una clave puede carecer de cuota o el modelo puede no estar disponible. En ese caso se revisa el modelo y el estado del proveedor sin guardar la clave en Git.

## 9. Componentes y configuración final

| Componente | Uso |
|---|---|
| Grupo de recursos | Agrupa plan, aplicación y configuración |
| ACR | Aloja `chat:v1` e `ia:v1` |
| Plan App Service Linux B1 | Ejecuta la aplicación Docker Compose |
| Aplicación web multicontenedor | Expone una URL única y mantiene la red interna |
| App settings | Configuran Gemini, Flask y SQLite |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true` | Habilita el almacenamiento persistente |
| `${WEBAPP_STORAGE_HOME}/chat:/data` | Conserva `chats.db` |

La entrega final debe ser un único ZIP con PDF, Markdown, capturas, Dockerfiles y Compose. Los archivos generados están en el ZIP sin contener secretos reales. Completa las capturas y la URL real antes de entregar.
