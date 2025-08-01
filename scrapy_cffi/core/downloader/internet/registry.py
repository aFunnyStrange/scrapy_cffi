_registry = {}

def register_request_class(cls):
    name = cls.__name__
    if name in _registry:
        raise ValueError(f"Request class '{name}' already registered.")
    _registry[name] = cls
    return cls

def get_request_class(class_name: str):
    cls = _registry.get(class_name)
    if cls is None:
        raise ValueError(f"Request class '{class_name}' not found in registry.")
    return cls

def is_registered(class_name: str) -> bool:
    return class_name in _registry

def clear_registry():
    _registry.clear()

def all_registered_names() -> list:
    return list(_registry.keys())
