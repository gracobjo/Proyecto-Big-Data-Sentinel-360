# Sentinel360 – Configurar el procesador InvokeHTTP (OpenWeather)

Con el procesador **InvokeHTTP** seleccionado, abre su configuración (doble clic o clic derecho → Configure) y ajusta estas propiedades.

---

## Propiedades obligatorias

| Propiedad      | Valor |
|----------------|--------|
| **HTTP Method** | `GET` |
| **URL**         | URL de la API. Opción 1 (con parámetro):<br>`https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=${openweather_api_key}&units=metric`<br>Opción 2 (pegar la key a mano, solo para pruebas): sustituye `TU_API_KEY` por tu clave:<br>`https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=TU_API_KEY&units=metric` |

- **lat=40.42&lon=-3.70**: Madrid (puedes cambiar por otra ciudad).
- **units=metric**: temperaturas en °C.
- Si usas **Parameter Context** en el grupo, crea el parámetro **`openweather_api_key`** (sensitive) con tu API key y usa en la URL: **`${openweather_api_key}`**.

---

## Propiedades recomendadas (Settings / Properties)

| Propiedad            | Valor recomendado |
|---------------------|--------------------|
| **Connection Timeout** | `5 secs` (o dejar por defecto) |
| **Read Timeout**      | `15 secs` (o dejar por defecto) |
| **Follow Redirects**  | `true` |
| **Penalize on No Retry** | `false` |

El resto se puede dejar por defecto.

---

## Relaciones (Relationships)

- **success**: conectar a **PublishKafka** (y/o **PutHDFS**). Es la salida cuando la API responde 2xx.
- **failure**, **no retry**, **client error**, **server error**: puedes dejarlas sin conectar o llevarlas a un **LogAttribute** / **PutFile** para depurar.

---

## Obtener API key de OpenWeather

1. Entra en [openweathermap.org](https://openweathermap.org/).
2. **Sign In** → **Create an Account** (cuenta gratuita).
3. En **API keys** (o en [API keys](https://home.openweathermap.org/api_keys)) copia la key y úsala en la URL o en el parámetro **`openweather_api_key`**.

---

## Resumen rápido

1. **HTTP Method**: `GET`
2. **URL**: `https://api.openweathermap.org/data/2.5/weather?lat=40.42&lon=-3.70&appid=${openweather_api_key}&units=metric`
3. En el **process group** → Configure → **Parameter context** → crear parámetro **`openweather_api_key`** (sensitive) con tu clave.
4. **Apply** / **OK** en InvokeHTTP.
5. Conectar **InvokeHTTP (success)** al siguiente procesador (PublishKafka o PutHDFS).
