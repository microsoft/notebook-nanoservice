# notebook_nanoservice
Nanoservices for notebooks.

Quickly and effortlessly expose your notebook's functions via a REST API. 

> **Note:** This library is designed to scaffold a small backend service for ease of development and prototyping purposes only. Not for production use.

## Features
* Hot functions - redefine your functions as you go without restarting the service.
* No decoration required.
* Auto serialization for primitive types, lists, Pandas dataframes, and images. Extensible for other types.
* Works with Jupyter & Spark notebooks, probably others.
* No dependency conflicts.
* API manifest in JSON or markdown, suitable for use with LLMs.

## Installation
```bash
pip install notebook-nanoservice
```

## Usage

### Initialize a server
```python
from notebook_nanoservice import NanoService
service = NanoService(globals())
service.start()
```

### View the manifest
Open http://localhost:5001 to see a JSON manifest of your API (the global functions in your notebook).
You may also see it in markdown at http://localhost:5001/?format=md

### Invoke a function
If you have a function such as:
```python
def concat(a, b):
    return a + b
```
It can be invoked at http://localhost:5001/api/concat?a=value1&b=value2

See [test/sample.ipynb](test/sample.ipynb) for examples of type casting the parameters.

### Stop and free up the port
```python
service.stop()
```

## API

### Constructor

The `NanoService` class is initialized to expose the global context of a Jupyter notebook or Python script via a REST API:

```python
NanoService(global_context, host, port, include_source)
```

#### Parameters
- `global_context` (dict, required): The global context to expose. Typically passed as `globals()` from the notebook or script.
- `host` (str, optional): The host address for the server. Defaults to `"127.0.0.1"`.
- `port` (int, optional): The port number for the server. Defaults to `5001`.
- `include_source` (bool, optional): Whether to include the source code of functions in the metadata. Defaults to `False`.

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
