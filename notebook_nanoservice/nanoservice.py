# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import math
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver

class NanoService:
    @property
    def port(self):
        return self._port

    @property
    def host(self):
        return self._host

    def __init__(self, global_context, host="127.0.0.1", port=5001, include_source=False):
        if not global_context:
            raise ValueError("global_context is required and cannot be None.")

        self._host = host
        self._port = port
        self._server = None
        self._thread = None
        self.global_context = global_context
        self.trace_enabled = False
        self.include_source = include_source
        self.ignore_functions = [
            #kernel
            "exit",
            "quit",
            
            #this class
            "NanoService",

            #jupyter
            "display",
            "get_ipython",
            "ipython_display",
            "open",
            
            #Fabric
            "custom_display",
            "initializeLHContext",
            "is_synapse_kernel",
            "prepare",
            "where_json",
        ]

    output_class_rules = {
        # we use strings instead of types to avoid dependency issues
        "pandas": lambda instance: (
            (
                instance.reset_index()
                if not (
                    instance.index.__class__.__name__ == "RangeIndex"
                    and instance.index.__repr__().startswith("RangeIndex(start=0")
                )
                else instance
            ).to_dict(orient="records"),
            'json'
        ) if instance.__class__.__module__ == "pandas.core.frame" and instance.__class__.__name__ == "DataFrame" else None,
        "spark": lambda instance: (
            instance.toPandas().to_dict(orient="records"), 'json'
        ) if instance.__class__.__module__ == "pyspark.sql.dataframe" and instance.__class__.__name__ == "DataFrame" else None,
        "PIL": lambda instance: (
            NanoService.convert_image_to_png_bytes(instance.save), 'image'
        ) if instance.__class__.__module__ == "PIL.Image" and instance.__class__.__name__ == "Image" else None,
        "matplotlib_figure": lambda instance: (
            NanoService.convert_image_to_png_bytes(instance.savefig), 'image'
        ) if instance.__class__.__module__ in ["matplotlib.figure", "seaborn.axisgrid"] and hasattr(instance, "savefig") else None,
        "matplotlib_pyplot": lambda instance: (
            NanoService.convert_image_to_png_bytes(instance.gcf().savefig), 'image'
        ) if instance.__name__ == "matplotlib.pyplot" else None,
    }

    sanitize_rules = {
        # Handle Spark TimestampType or similar
        "spark": lambda obj: (
            obj.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ) if hasattr(obj, "strftime") else None,
    }
    
    def get_notebook_api(self, handler, query_params):
        import inspect
        self.trace_enabled = query_params.get("trace_enabled", ["false"])[0].lower() == "true"
        format_type = query_params.get("format", ["json"])[0].lower()

        nano_api = {}

        if self.global_context:
            for name, obj in self.global_context.items():
                if name not in self.ignore_functions and callable(obj) and not isinstance(obj, type):
                    try:
                        if hasattr(obj, '__code__') or hasattr(obj, '__func__'):
                            sig = inspect.signature(obj)
                            nano_api[name] = {
                                "signature": str(sig),
                                "source": "(unavailable)",
                                "doc": obj.__doc__ or "",
                                "return": str(sig.return_annotation) if sig.return_annotation != inspect._empty else "",
                                "params": self._extract_parameters(sig)
                            }
                            if self.include_source:
                                nano_api[name]["source"] = inspect.getsource(obj)
                    except Exception:
                        pass
        else:
            nano_api = {"error": "No global context found."}

        if format_type == "openapi":
            # Extract base_url parameter for OpenAPI spec generation
            base_url = query_params.get("base_url", [None])[0]
            # If no base_url provided, construct from server host/port
            if not base_url:
                protocol = 'https' if handler.headers.get('X-Forwarded-Proto') == 'https' else 'http'
                host_header = handler.headers.get('Host')
                if host_header:
                    base_url = f"{protocol}://{host_header}"                
                else:
                    base_url = f"http://{self._host}:{self._port}"
            openapi_spec = NanoService.generate_openapi_spec(nano_api, base_url)
            handler._send_response(200, json.dumps(openapi_spec), "application/json")
        elif format_type == "md":
            md_output = self.generate_markdown(nano_api)
            handler._send_response(200, md_output, "text/markdown")
        else:
            handler._send_response(200, json.dumps({"trace_enabled": self.trace_enabled, "api": nano_api}), "application/json")

    def _call_function(self, handler, function_name, params, trace):
        import inspect
        func = self.global_context.get(function_name)

        if func and callable(func):
            # Normalize parameter names by removing '[]' suffix for list parameters
            kwargs = {}
            for key, value in params.items():
                normalized_key = key.rstrip("[]")  # Remove '[]' suffix if present
                if normalized_key in kwargs:
                    kwargs[normalized_key].extend(value if isinstance(value, list) else [value])
                else:
                    kwargs[normalized_key] = value if isinstance(value, list) else [value]

            # Flatten single-item lists for non-list parameters
            kwargs = {key: value[0] if len(value) == 1 else value for key, value in kwargs.items()}

            sig = inspect.signature(func)
            trace.append(f"Function signature: {sig}")

            from typing import get_origin, List

            for key, value in list(kwargs.items()):
                param = sig.parameters.get(key)
                if param:
                    try:
                        if get_origin(param.annotation) == list or param.annotation == List:
                            inner_type = param.annotation.__args__[0] if hasattr(param.annotation, '__args__') else str
                            kwargs[key] = [inner_type(v) for v in value] if isinstance(value, list) else [inner_type(value)]
                        elif param.annotation != inspect._empty:
                            if param.annotation in [int, float, str]:
                                kwargs[key] = param.annotation(value)
                            elif param.annotation == bool:
                                kwargs[key] = value.lower() in ['true', '1', 'yes'] if isinstance(value, str) else bool(value)
                        elif param.default != inspect._empty:
                            if isinstance(param.default, (int, float)):
                                kwargs[key] = type(param.default)(value)
                            elif isinstance(param.default, bool):
                                kwargs[key] = value.lower() in ['true', '1', 'yes'] if isinstance(value, str) else bool(value)
                    except (ValueError, TypeError) as e:
                        trace.append(f"Error converting value for '{key}': {str(e)}")
                        raise self.DetailedHTTPException(400, f"Invalid value for parameter '{key}': {str(e)}", trace)
                else:
                    trace.append(f"Unrecognized parameter '{key}' provided.")
                    kwargs.pop(key)

            trace.append(f"Final parameters for function call: {kwargs}")
            try:
                output_type = 'json'
                output = func(**kwargs)
                if output is not None and hasattr(output, "__class__") and hasattr(output.__class__, "__module__"):
                    for rule_name, rule_func in self.output_class_rules.items():
                        try:
                            result = rule_func(output)
                        except Exception as e:
                            trace.append(f"Error applying output class rule '{rule_name}': {str(e)}")
                            result = None
                        if result:
                            output, output_type = result
                            break
                if (output_type == 'json'):
                    # Ensure all output is sanitized
                    output = self.sanitize_for_json(output, trace)
                    output_str = f"{output}"
                    if len(output_str) > 2000:
                        output_str = output_str[:2000] + "..."
                    trace.append(f"Function executed successfully with output: {output_str}")
                    handler._send_response(200, json.dumps({"trace": "\n".join(trace), "output": output} if self.trace_enabled else output))
                elif (output_type == 'image'):
                    handler._send_response(200, output, "image/png")

            except TypeError as e:
                trace.append(f"Type error in function call: {str(e)}")
                raise self.DetailedHTTPException(400, f"Type mismatch in function '{function_name}': {str(e)}", trace)
            except Exception as e:
                trace.append(f"Unexpected error: {str(e)}")
                raise self.DetailedHTTPException(500, f"Unexpected error in function '{function_name}': {str(e)}", trace)
        else:
            trace.append("Function not found or not callable.")
            raise self.DetailedHTTPException(404, f"Function '{function_name}' not found", trace)

    def start(self):
        from threading import Thread
        import socket

        # Check if the port is available without binding to it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                result = sock.connect_ex((self._host, self._port))
                if result == 0:
                    raise RuntimeError(f"Port {self._port} is already in use.")
            except Exception as e:
                # Only raise if it's not "connection refused" (port is free)
                if isinstance(e, OSError):
                    pass
                else:
                    raise

        self._server = self.ThreadedHTTPServer((self._host, self._port), self.RequestHandler)
        self._server.nanoservice_instance = self
        self._thread = Thread(target=self._server.serve_forever)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join()
            self._thread = None

    class RequestHandler(BaseHTTPRequestHandler):
        def _send_response(self, status_code, content, content_type="application/json"):
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")  # CORS support
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
            if content:
                self.wfile.write(content.encode("utf-8") if isinstance(content, str) else content)

        def do_OPTIONS(self):
            self._send_response(204, None)

        def do_GET(self):
            try:
                from urllib.parse import urlparse, parse_qs
                parsed_path = urlparse(self.path)
                query_params = parse_qs(parsed_path.query)
                path = parsed_path.path.strip("/")

                if path == "":  # Root route
                    self.server.nanoservice_instance.get_notebook_api(self, query_params)
                elif path == "api":  # Exact match for '/api/'
                    self.server.nanoservice_instance.get_notebook_api(self, query_params)
                elif path.startswith("api/"):
                    path = path[4:]  # Remove the 'api/' prefix
                    if path == "":  # Root route under 'api'
                        self.server.nanoservice_instance.get_notebook_api(self, query_params)
                    else:  # Wildcard route under 'api'
                        trace = ["Received GET request URL: " + self.path]
                        self.server.nanoservice_instance._call_function(self, path, query_params, trace)
                else:
                    self._send_response(404, json.dumps({"detail": "Not Found"}))
            except NanoService.DetailedHTTPException as e:
                self._send_response(e.status_code, json.dumps(e.detail))
            except Exception as e:
                error_response = {"detail": "An unexpected error occurred", "details": str(e)}
                self._send_response(500, json.dumps(error_response))

        def do_POST(self):
            try:
                from urllib.parse import urlparse
                parsed_path = urlparse(self.path)
                path = parsed_path.path.strip("/")
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body) if body else {}

                if path == "":  # Root route (not typically used for POST)
                    self._send_response(405, json.dumps({"detail": "POST not allowed on root route"}))
                elif path == "api":  # Exact match for '/api/'
                    self._send_response(405, json.dumps({"detail": "POST not allowed on root route"}))
                elif path.startswith("api/"):
                    path = path[4:]  # Remove the 'api/' prefix
                    if path == "":  # Root route under 'api'
                        self._send_response(405, json.dumps({"detail": "POST not allowed on root route"}))
                    else:  # Wildcard route under 'api'
                        trace = ["Received POST request URL: " + self.path]
                        self.server.nanoservice_instance._call_function(self, path, data, trace)
                else:
                    self._send_response(404, json.dumps({"detail": "Not Found"}))
            except json.JSONDecodeError:
                self._send_response(400, json.dumps({"detail": "Invalid JSON in request body"}))
            except NanoService.DetailedHTTPException as e:
                self._send_response(e.status_code, json.dumps(e.detail))
            except Exception as e:
                error_response = {"detail": "An unexpected error occurred", "details": str(e)}
                self._send_response(500, json.dumps(error_response))

    class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
        """A multithreaded HTTP server."""
        daemon_threads = True  # Ensure threads are cleaned up when the server shuts down

    class DetailedHTTPException(Exception):
        """Exception class for detailed HTTP errors."""
        def __init__(self, status_code: int, detail: str, trace: list = None):
            self.status_code = status_code
            self.detail = {"detail": detail, "trace": trace or []}

    @staticmethod
    def sanitize_for_json(value, trace):
        if isinstance(value, dict):
            return {k: NanoService.sanitize_for_json(v, trace) for k, v in value.items()}
        elif isinstance(value, list):
            return [NanoService.sanitize_for_json(v, trace) for v in value]
        elif hasattr(value, "isoformat"):  # Handle datetime-like objects
            return value.isoformat()
        elif isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
        else:
            # Apply custom sanitization rules
            for rule_name, rule_func in NanoService.sanitize_rules.items():
                try:
                    result = rule_func(value)
                except Exception as e:
                    trace.append(f"Error applying sanitize rule '{rule_name}': {str(e)}")
                    result = None
                if result is not None:
                    return result
        return value

    @staticmethod
    def convert_image_to_png_bytes(method_callable):
        import io
        img_io = io.BytesIO()
        method_callable(img_io, format='PNG')
        img_io.seek(0)
        return img_io.getvalue()

    @staticmethod
    def generate_markdown(nano_api):
        none_placeholder = "**none**"
        unknown_placeholder = "**unknown**"
        md_output = "# API nano_api\n\n"
        for name, details in nano_api.items():
            md_output += f"## [/api/{name}](/api/{name})\n"
            md_output += f"### Signature\n{details.get('signature', '')}\n\n"
            doc = details.get('doc', none_placeholder) or none_placeholder
            return_annotation = details.get('return', unknown_placeholder) or unknown_placeholder
            md_output += f"### Documentation\n{doc}\n\n"
            md_output += f"### Return\n{return_annotation}\n\n"
        return md_output

    @staticmethod
    def generate_openapi_spec(nano_api, base_url=None):
        """Generate a minimal OpenAPI 3.0 specification from nano_api."""
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Notebook Nanoservice API",
                "version": "1.0.0"
            },
            "paths": {}
        }
        
        # Add servers section with base URL if provided
        if base_url:
            spec["servers"] = [{"url": base_url}]
        
        # Skip if there's an error in nano_api
        if "error" in nano_api:
            return spec
            
        for function_name, function_info in nano_api.items():
            path = f"/api/{function_name}"
            
            # Basic parameter processing
            parameters = []
            request_body = None
            
            # Convert nano_api params to OpenAPI parameters
            for param in function_info.get("params", []):
                if param["type"] == "array":
                    # For GET requests, arrays use the [] suffix notation
                    parameters.append({
                        "name": f"{param['name']}[]",
                        "in": "query",
                        "required": param["required"],
                        "schema": {
                            "type": "array",
                            "items": param.get("items", {"type": "string"})
                        }
                    })
                else:
                    parameters.append({
                        "name": param["name"],
                        "in": "query", 
                        "required": param["required"],
                        "schema": {"type": param["type"]}
                    })
            
            # Create request body schema for POST requests
            if function_info.get("params"):
                properties = {}
                required_fields = []
                
                for param in function_info["params"]:
                    if param["type"] == "array":
                        properties[param["name"]] = {
                            "type": "array",
                            "items": param.get("items", {"type": "string"})
                        }
                    else:
                        properties[param["name"]] = {"type": param["type"]}
                    
                    if param["required"]:
                        required_fields.append(param["name"])
                
                if properties:
                    request_body = {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": properties
                                }
                            }
                        }
                    }
                    if required_fields:
                        request_body["content"]["application/json"]["schema"]["required"] = required_fields
            
            # Determine response content type based on function return type or common patterns
            response_content = {"application/json": {"schema": {"type": "object"}}}
            
            # Check if function likely returns an image based on name patterns
            if any(keyword in function_name.lower() for keyword in ['image', 'chart', 'plot', 'graph', 'heatmap']):
                response_content["image/png"] = {"schema": {"type": "string", "format": "binary"}}
            
            # Create path operations
            spec["paths"][path] = {}
            
            # GET operation
            get_op = {
                "summary": function_info.get("doc") or f"Execute {function_name}",
                "parameters": parameters,
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": response_content
                    }
                }
            }
            spec["paths"][path]["get"] = get_op
            
            # POST operation
            post_op = {
                "summary": function_info.get("doc") or f"Execute {function_name}",
                "responses": {
                    "200": {
                        "description": "Successful response", 
                        "content": response_content
                    }
                }
            }
            if request_body:
                post_op["requestBody"] = request_body
                
            spec["paths"][path]["post"] = post_op
        
        return spec

    def _extract_parameters(self, sig):
        """Extract parameter information from function signature for OpenAPI spec."""
        import inspect
        from typing import get_origin, List
        
        params = []
        for param_name, param in sig.parameters.items():
            param_info = {
                "name": param_name,
                "required": param.default == inspect.Parameter.empty,
                "type": "string"  # default type
            }
            
            # Determine parameter type from annotation
            if param.annotation != inspect._empty:
                if param.annotation == int:
                    param_info["type"] = "integer"
                elif param.annotation == float:
                    param_info["type"] = "number"
                elif param.annotation == bool:
                    param_info["type"] = "boolean"
                elif param.annotation == str:
                    param_info["type"] = "string"
                elif get_origin(param.annotation) == list or param.annotation == List:
                    param_info["type"] = "array"
                    # Try to get the inner type for arrays
                    if hasattr(param.annotation, '__args__') and param.annotation.__args__:
                        inner_type = param.annotation.__args__[0]
                        if inner_type == int:
                            param_info["items"] = {"type": "integer"}
                        elif inner_type == float:
                            param_info["items"] = {"type": "number"}
                        elif inner_type == str:
                            param_info["items"] = {"type": "string"}
                        else:
                            param_info["items"] = {"type": "string"}
                    else:
                        param_info["items"] = {"type": "string"}
            elif param.default != inspect.Parameter.empty:
                # Infer type from default value
                if isinstance(param.default, int):
                    param_info["type"] = "integer"
                elif isinstance(param.default, float):
                    param_info["type"] = "number"
                elif isinstance(param.default, bool):
                    param_info["type"] = "boolean"
                elif isinstance(param.default, str):
                    param_info["type"] = "string"
            
            params.append(param_info)
        
        return params