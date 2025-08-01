import hashlib, json, json5, orjson, re, regex
from typing import Any, List, Dict, Union, Tuple
from parsel import Selector as ParselSelector
import blackboxprotobuf
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .internet import HttpResponse

def extract_nested_objects(
    text: str,
    key: str = "",
    re_rule: str = ""
) -> List[Any]:
    if re_rule:
        return regex.findall(re_rule, text, regex.S)

    objects = []

    if key:
        escaped_key = regex.escape(key)

        # support {}
        object_pat = rf'"{escaped_key}"\s*:\s*(\{{(?:[^{{}}]+|(?1))*\}})'
        # support []
        array_pat = rf'"{escaped_key}"\s*:\s*(\[(?:[^\[\]]+|(?1))*\])'
        # Supports basic values: string, number, null, and boolean
        literal_pat = rf'"{escaped_key}"\s*:\s*(".*?"|\d+(?:\.\d+)?|true|false|null)'

        for pat in [object_pat, array_pat, literal_pat]:
            matches = regex.findall(pat, text, regex.S | regex.I)
            for m in matches:
                try:
                    objects.append(json.loads(m))
                except Exception:
                    pass
    else:
        # If no key is provided, extract all top-level JSON objects or arrays
        block_pat = r'(\{(?:[^{}]+|(?1))*\}|\[(?:[^\[\]]+|(?1))*\])'
        matches = regex.findall(block_pat, text, regex.S)
        for m in matches:
            try:
                objects.append(json.loads(m))
            except Exception:
                pass

    return objects[0] if len(objects) == 1 else objects

def extract_nested_objects_deep(text: str, key: str = "", strict_level: int = 2, re_rule: str = "") -> Union[None, Dict, List[Dict], List[str]]:
    if re_rule:
        return re.findall(re_rule, text, re.S)

    seen_json_texts = set()
    seen_str_json = set()
    seen_obj_hashes = set()

    def remove_json_comments(text: str) -> str:
        text = re.sub(r'//.*?(?=\n|$)', '', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        return text

    def hash_obj(obj: Any) -> str:
        try:
            dumped = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(dumped.encode('utf-8')).hexdigest()
        except Exception:
            return str(id(obj))

    def try_parse_json_recursive(json_str: str, max_depth: int = 5) -> Union[Dict, List, None]:
        json_str = json_str.strip()
        json_str = remove_json_comments(json_str)
        if not isinstance(json_str, str) or ':' not in json_str or json_str in seen_json_texts:
            return None
        seen_json_texts.add(json_str)

        parsers = []
        if strict_level == 2:
            parsers = [orjson.loads]
        elif strict_level == 1:
            parsers = [json.loads]
        elif strict_level == 0:
            parsers = [json.loads, json5.loads]

        for _ in range(max_depth):
            for parser in parsers:
                try:
                    result = parser(json_str)
                    if isinstance(result, (dict, list)):
                        return result
                    elif isinstance(result, str):
                        json_str = result
                        break
                except Exception:
                    continue
        return None

    def find_key_recursively(obj: Any, target_key: str) -> List[Any]:
        matches = []
        if isinstance(obj, (Dict, list)):
            obj_hash = hash_obj(obj)
            if obj_hash in seen_obj_hashes:
                return matches
            seen_obj_hashes.add(obj_hash)
        if isinstance(obj, Dict):
            if not target_key:
                matches.append(obj)
            for k, v in obj.items():
                if k == target_key:
                    matches.append(v)
                matches.extend(find_key_recursively(v, target_key))
                if isinstance(v, str) and "{" in v and "}" in v:
                    parsed = try_parse_json_recursive(v)
                    if parsed:
                        matches.extend(find_key_recursively(parsed, target_key))
        elif isinstance(obj, list):
            for item in obj:
                matches.extend(find_key_recursively(item, target_key))
        elif isinstance(obj, str):
            if obj in seen_str_json:
                return matches
            seen_str_json.add(obj)
            parsed = try_parse_json_recursive(obj)
            if parsed:
                matches.extend(find_key_recursively(parsed, target_key))
        return matches

    top_obj = try_parse_json_recursive(text)
    if top_obj:
        matches = find_key_recursively(top_obj, key)
        if matches:
            return matches if len(matches) > 1 else matches[0]

    def find_brace_pairs_safe(text: str) -> List[Any]:
        stack = []
        results = []
        for i, char in enumerate(text):
            if char == '{':
                stack.append(i)
            elif char == '}':
                if stack:
                    start = stack.pop()
                    candidate = text[start:i+1]
                    obj = try_parse_json_recursive(candidate)
                    if obj is not None:
                        results.append(obj)
        return results

    json_objects = find_brace_pairs_safe(text)
    if not key:
        return json_objects

    all_matches = []
    for obj in json_objects:
        all_matches.extend(find_key_recursively(obj, key))

    if not all_matches:
        return None
    elif len(all_matches) == 1:
        return all_matches[0]
    return all_matches

class Selector(ParselSelector):
    def __init__(self, response: "HttpResponse"=None, type=None, **kwargs):
        if not response:
            raise ValueError("[Selector] Missing response")
        self.response = response
        self.text = response.text
        super().__init__(text=self.text, type=type or "html", **kwargs)

    def extract_json(self, key: str="", re_rule: str=""):
        return extract_nested_objects(text=self.text, key=key, re_rule=re_rule)

    def extract_json_strong(self, key=None, strict_level=2, re_rule=""):
        return extract_nested_objects_deep(text=self.text, key=key, strict_level=strict_level, re_rule=re_rule)

    def decode_protobuf(self) -> Tuple[Dict, Dict]:
        return blackboxprotobuf.decode_message(self.response.content)
    
if __name__ == "__main__": 
    data = """
        <html>
            <head>...</head>
            <body>
                "{"
                <div ... class="{">
                    {
                        "a": 1,
                        "b": "2",
                        "c": [0, "3", {"_a": 4, "_b": "5"}],
                        "d": {"d0": 6, "d1": "7"},
                        "level1": {
                            "raw": "{\\"key\\": {\\"deep\\": \\"value\\"}}"
                        }
                    }
                    "{"
                    <div ... class="{">
                        {
                            "a": {"d0": 14, "d2": "15"},
                            "e": 8,
                            "f": "9",
                            "g": [10, "11", {"_a": 12, "_b": "13"}],
                            "logs": [
                                "{\\"event\\": \\"click\\", \\"meta\\": {\\"target\\": \\"button\\"}}",
                                "{\\"event\\": \\"scroll\\", \\"meta\\": {\\"target\\": \\"window\\"}}"
                            ]
                        }
                    </div>
                </div>
                {
                    "h": {"d0": 16, "d2": "17"}, // no quotes!
                    "e": 18,
                    "i": "19,
                    "j": [20, "21", {"_a": 22, "_b": "23"}],
                    "logs": [
                        "{\\"event\\": \\"click\\", \\"meta\\": {\\"target\\": \\"button\\"}}",
                        "{\\"event\\": \\"scroll\\", \\"meta\\": {\\"target\\": \\"window\\"}}"
                    ]
                }
                "}"
                {
                    "k": {"d0": 24, "d2": "25"},
                    "l": 26,
                    "m": "27,
                    "n": [28, "29", {"_a": 30, "_b": "31"}],
                    "o": '{bad: "json"}',
                "}"
            </body>
        </html>
    """
    # print(extract_nested_objects(text=data, key="a")) # [{'d0': 14, 'd2': '15'}, 1]
    # print(extract_nested_objects(text=data, key="_a")) # [4, 12, 22, 30]
    # print(extract_nested_objects(text=data, key="c")) # [0, '3', {'_a': 4, '_b': '5'}]
    # print(extract_nested_objects(text=data, key="e")) # [8, 18]
    # print(extract_nested_objects(text=data, key="raw")) # []
    # print(extract_nested_objects(text=data, key="key")) # []
    # print(extract_nested_objects(text=data, key="deep")) # []
    # print(extract_nested_objects(text=data, key="event")) # []
    # print(extract_nested_objects(text=data, key="target")) # []

    print(extract_nested_objects_deep(text=data, key="a")) # [1, {'d0': 14, 'd2': '15'}]
    print(extract_nested_objects_deep(text=data, key="_a")) # [4, 12, 22, 30]
    print(extract_nested_objects_deep(text=data, key="c")) # [0, '3', {'_a': 4, '_b': '5'}]
    print(extract_nested_objects_deep(text=data, key="e", strict_level=0)) # 8
    print(extract_nested_objects_deep(text=data, key="raw")) # {"key": {"deep": "value"}}
    print(extract_nested_objects_deep(text=data, key="key")) # {'deep': 'value'}
    print(extract_nested_objects_deep(text=data, key="deep")) # value
    print(extract_nested_objects_deep(text=data, key="event")) # ['click', 'scroll']
    print(extract_nested_objects_deep(text=data, key="target")) # ['button', 'window']