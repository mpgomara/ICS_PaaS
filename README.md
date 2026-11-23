# Chat Gemini con Docker Compose en Azure App Service

Aplicación PaaS para el **caso 3** de la práctica:

- **Contenedor `chat`:** interfaz web de chat, historial persistente en SQLite, títulos editables y envío de mensajes al contenedor IA.
- **Contenedor `ia`:** API privada Flask que recibe mensajes, los convierte en una petición a Gemini y devuelve la respuesta.

Solo `chat` está publicado hacia Internet. `ia` se comunica con `chat` dentro de la red interna de Compose usando `http://ia:8000`. La clave de Gemini se configura como secreto de App Service y no se copia a las imágenes.

## Despliegue local

1. Crea la configuración:

   ```sh
   cp .env.example .env
   ```

   Sustituye las variables ficticias por una clave Gemini nueva y una clave aleatoria de Flask. La clave Gemini proporcionada originalmente debe considerarse expuesta y revocarse.

2. Construye y ejecuta el Compose local:

   ```sh
   docker compose -f compose.local.yaml up --build -d
   ```

3. Abre `http://localhost:8080`, crea varios chats, cambia sus títulos y prueba el envío de mensajes.

4. Comprueba persistencia y logs:

   ```sh
   docker compose -f compose.local.yaml ps
   docker compose -f compose.local.yaml logs -f chat ia
   docker compose -f compose.local.yaml restart chat
   ```

   Las conversaciones deben seguir disponibles tras reiniciar `chat`. Detén la aplicación conservando los datos:

   ```sh
   docker compose -f compose.local.yaml down
   ```

## Despliegue en Azure App Service

El proceso completo, los recursos, los comandos y las capturas requeridas están en [Memoria_PaaS.md](Memoria_PaaS.md) y en su [PDF](Memoria_PaaS.pdf).

La topología del caso 3 usa:

1. Un grupo de recursos.
2. Azure Container Registry (ACR) con las imágenes `chat:v1` e `ia:v1`.
3. Un plan Linux de App Service.
4. Una aplicación web configurada con Compose multicontenedor.
5. `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true` y un volumen bajo `${WEBAPP_STORAGE_HOME}` para SQLite.

App Service no admite `build` en Compose. Las imágenes se construyen y suben primero al ACR. Solo se publica el puerto 8080 de `chat`; `ia` no tiene puerto público.

## Archivos principales

- [compose.yaml](compose.yaml): Compose definitivo para App Service, con imágenes ACR y persistencia App Service.
- [compose.local.yaml](compose.local.yaml): Compose local que construye ambas imágenes.
- [chat_service/Dockerfile](chat_service/Dockerfile): imagen del cliente web.
- [ai_service/Dockerfile](ai_service/Dockerfile): imagen del adaptador Gemini.
- [Memoria_PaaS.md](Memoria_PaaS.md): fuente de la memoria.
- [Memoria_PaaS.pdf](Memoria_PaaS.pdf): memoria para entregar.

## Variables

| Variable | Servicio | Valor local | Valor Azure |
|---|---|---|---|
| `GEMINI_API_KEY` | `ia` | `.env` | Secreto de App Service |
| `GEMINI_MODEL` | `ia` | `.env`, por defecto `gemini-2.5-flash` | App setting |
| `AI_SERVICE_URL` | `chat` | `http://ia:8000` | `http://ia:8000` |
| `DATABASE_PATH` | `chat` | `/data/chats.db` | `/data/chats.db` |
| `FLASK_SECRET_KEY` | `chat` | `.env` | Secreto de App Service |
