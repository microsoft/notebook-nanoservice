# notebook_nanoservice
Nanoservices for notebooks.

Quickly and effortlessly expose your notebook's capabilities via a REST API. 

Combine with Ngrok to share your notebook's functionality with others.

This library is not intended for production use, but it provides a low-friction way to prototype a small backend service.

## Features
* Hot functions - redefine your functions as you go without restarting the service.
* No decoration required, all functions are exposed.
* Auto serialization for primitive types, lists, Pandas dataframes, and images. Extensible for other types.
* Works with Jupyter & Spark notebooks, probably others.
* Tiny footprint without requirements.

## Installation
```bash
pip install notebook-nanoservice
```

## Usage (on localhost)
Initialize a server:
```python
from notebook_nanoservice import NanoService
service = NanoService(globals())
service.start()
```

Stop and free up the port:
```python
service.stop()
```

## Combine with ngrok
The [pyngrok](https://pyngrok.readthedocs.io/) library is multithreaded and will not "lock up" your notebook kernel.

```bash
pip install pyngrok
```

Initialize a server:
```python
from notebook_nanoservice import NanoService
service = NanoService(globals())
service.start()

from pyngrok import ngrok
ngrok.set_auth_token(os.getenv("NGROK_AUTHTOKEN"))

tunnel = ngrok.connect(service.port)
print("Public URL:", tunnel.public_url)
```

Stop and free up the port and tunnel:
```python
ngrok.kill()
service.stop()
```

## API

### Constructor

The `NanoService` class is initialized to expose the global context of a Jupyter notebook or Python script via a REST API:

```python
NanoService(global_context, host, port)
```

#### Parameters
- `global_context` (dict, required): The global context to expose. Typically passed as `globals()` from the notebook or script.
- `host` (str, optional): The host address for the server. Defaults to `"127.0.0.1"`.
- `port` (int, optional): The port number for the server. Defaults to `5001`.

Multiple service instances can run simultaneously by having unique port numbers.
```python
# in a different notebook
from notebook_nanoservice import NanoService
service = NanoService(globals(), port=5002)
service.start()
```

### ignore_functions

By default, all user-defined functions are exposed via the REST API. The `ignore_functions` property is a list of function names that the server will ignore when exposing the global context. By default, it includes functions like `exit`, `quit`, and others that are not meant to be exposed.

You can append to this list to exclude additional functions from being exposed. For example:

```python
service.ignore_functions.append("my_function_to_ignore")
```

## Contributing
Contributions are welcome! Please submit a pull request or open an issue on the [GitHub repository](https://github.com/microsoft/notebook-nanoservice).

## Development
Install development dependencies:
```bash
pip install -r requirements.txt
```

Install the package locally:
Open [test/local_install.ipynb](test/local_install.ipynb) and follow instructions within.

## License
This project is licensed under the MIT License. See the LICENSE file for details.