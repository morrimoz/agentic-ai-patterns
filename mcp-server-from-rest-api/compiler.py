"""OpenAPI operations to exact MCP schemas. Server-bound headers stay out of model args."""

from copy import deepcopy
from dataclasses import dataclass
from urllib.parse import quote

from jsonschema import Draft202012Validator


@dataclass
class Operation:
    name: str
    method: str
    path: str
    description: str
    schema: dict
    locations: dict
    effect: str


class Compiler:
    def __init__(self, spec):
        self.spec = spec
        self.by_name = {}
        for path, item in spec["paths"].items():
            for method, operation in item.items():
                if method not in {"get", "post"}:
                    raise ValueError("Unsupported OpenAPI method")
                properties = {}
                required = []
                locations = {}
                for parameter in item.get("parameters", []) + operation.get("parameters", []):
                    parameter = self.resolve(parameter)
                    if parameter["in"] == "header":
                        continue
                    if parameter["in"] not in {"path", "query"}:
                        raise ValueError("Unsupported parameter location")
                    name = parameter["name"]
                    properties[name] = self.resolve(parameter["schema"])
                    locations[name] = parameter["in"]
                    if parameter.get("required"):
                        required.append(name)
                if "requestBody" in operation:
                    body = self.resolve(operation["requestBody"])
                    if set(body["content"]) != {"application/json"}:
                        raise ValueError("Only JSON bodies are supported")
                    properties["body"] = self.resolve(body["content"]["application/json"]["schema"])
                    if body.get("required"):
                        required.append("body")
                schema = {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                }
                Draft202012Validator.check_schema(schema)
                name = operation["operationId"]
                if name in self.by_name:
                    raise ValueError("Duplicate operation identity")
                effect = operation.get("x-effect", "read" if method == "get" else "write")
                self.by_name[name] = Operation(
                    name, method.upper(), path, operation.get("summary", name), schema, locations, effect
                )

    def resolve(self, value, seen=()):
        if isinstance(value, list):
            return [self.resolve(item, seen) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            reference = value["$ref"]
            if not reference.startswith("#/") or reference in seen:
                raise ValueError("External or cyclic schema reference unsupported")
            target = self.spec
            for part in reference[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            resolved = self.resolve(deepcopy(target), (*seen, reference))
            return {**resolved, **self.resolve({k: v for k, v in value.items() if k != "$ref"}, seen)}
        return {key: self.resolve(item, seen) for key, item in value.items()}

    def tools(self):
        from mcp.types import Tool

        return [
            Tool(name=op.name, description=op.description, inputSchema=op.schema)
            for op in self.by_name.values()
        ]

    def request(self, name, args):
        if name not in self.by_name:
            raise ValueError("Unknown API tool")
        operation = self.by_name[name]
        Draft202012Validator(operation.schema).validate(args)
        path = operation.path
        query = {}
        for key, location in operation.locations.items():
            if key not in args:
                continue
            if location == "path":
                path = path.replace("{" + key + "}", quote(str(args[key]), safe=""))
            else:
                query[key] = args[key]
        return operation, path, query, args.get("body")
