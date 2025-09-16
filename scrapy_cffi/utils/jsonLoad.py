import hashlib, json, json5, orjson, re
from typing import Any, List, Dict, Union
import hashlib, json, json5, orjson, re, regex
from typing import Any, List, Dict, Union

def extract_nested_objects(
    text: str,
    key: str = "",
    re_rule: str = ""
) -> Union[List[Union[Dict, str]], Dict, str]:
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

class JSONExtractor:
    def __init__(self, strict_level: int = 2):
        self.strict_level = strict_level
        self.seen_json_texts = set()
        self.seen_str_json = set()
        self.seen_obj_hashes = set()

    def remove_json_comments(self, text: str) -> str:
        text = re.sub(r'//.*?(?=\n|$)', '', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        return text

    def hash_obj(self, obj: Any) -> str:
        try:
            dumped = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(dumped.encode('utf-8')).hexdigest()
        except Exception:
            return str(id(obj))

    def try_parse_json_recursive(self, json_str: str, max_depth: int = 5) -> Union[Dict, List, None]:
        json_str = json_str.strip()
        json_str = self.remove_json_comments(json_str)
        if not isinstance(json_str, str) or ':' not in json_str or json_str in self.seen_json_texts:
            return None
        self.seen_json_texts.add(json_str)

        parsers = []
        if self.strict_level == 2:
            parsers = [orjson.loads]
        elif self.strict_level == 1:
            parsers = [json.loads]
        elif self.strict_level == 0:
            parsers = [json.loads, json5.loads]

        for _ in range(max_depth):
            parsed = None
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

            if parsed is None:
                unescaped = json_str.replace(r'\"', '"').replace(r'\\', '\\')
            for parser in parsers:
                try:
                    parsed = parser(unescaped)
                    break
                except Exception:
                    continue

            if parsed is None:
                return None

            if isinstance(parsed, (dict, list)):
                return parsed
            elif isinstance(parsed, str):
                json_str = parsed
                continue
        return None

    def find_key_recursively(self, obj: Any, target_key: str) -> List[Any]:
        matches = []
        if isinstance(obj, (Dict, list)):
            obj_hash = self.hash_obj(obj)
            if obj_hash in self.seen_obj_hashes:
                return matches
            self.seen_obj_hashes.add(obj_hash)

        if isinstance(obj, Dict):
            if not target_key:
                matches.append(obj)
            for k, v in obj.items():
                if k == target_key:
                    matches.append(v)
                matches.extend(self.find_key_recursively(v, target_key))
                if isinstance(v, str) and "{" in v and "}" in v:
                    parsed = self.try_parse_json_recursive(v)
                    if parsed:
                        matches.extend(self.find_key_recursively(parsed, target_key))
        elif isinstance(obj, list):
            for item in obj:
                matches.extend(self.find_key_recursively(item, target_key))
        elif isinstance(obj, str):
            if obj in self.seen_str_json:
                return matches
            self.seen_str_json.add(obj)
            parsed = self.try_parse_json_recursive(obj)
            if parsed:
                matches.extend(self.find_key_recursively(parsed, target_key))
        return matches

    def find_brace_pairs_safe(self, text: str) -> List[Any]:
        stack = []
        results = []
        for i, char in enumerate(text):
            if char == '{':
                stack.append(i)
            elif char == '}':
                if stack:
                    start = stack.pop()
                    candidate = text[start:i+1]
                    obj = self.try_parse_json_recursive(candidate)
                    if obj is not None:
                        results.append(obj)
        return results

    def extract(self, text: str, key: str = "", re_rule: str = "") -> Union[List[Union[Dict, str]], Dict, str]:
        self.seen_json_texts = set()
        self.seen_str_json = set()
        self.seen_obj_hashes = set()

        if re_rule:
            return regex.findall(re_rule, text, regex.S)

        top_obj = self.try_parse_json_recursive(text)
        if top_obj:
            matches = self.find_key_recursively(top_obj, key)
            if matches:
                return matches if len(matches) > 1 else matches[0]

        json_objects = self.find_brace_pairs_safe(text)
        if not key:
            return json_objects

        all_matches = []
        for obj in json_objects:
            all_matches.extend(self.find_key_recursively(obj, key))
        return all_matches[0] if len(all_matches) == 1 else all_matches

class JSONScanner(JSONExtractor):
    def __init__(self, strict_level: int = 2):
        super().__init__(strict_level=strict_level)

    def scan_text(self, text: str, key: str = "", re_rule: str = "") -> Union[List[Union[Dict, str]], Dict, str]:
        results = self.extract(text=text, key=key, re_rule=re_rule)
        if results:
            return results

        top_obj = self.extract(text=text)
        if not top_obj:
            return []

        stack = [top_obj] if isinstance(top_obj, (dict, list)) else []
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for v in current.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
                    elif isinstance(v, str):
                        inner_res = self.extract(text=v, key=key)
                        if inner_res is not None:
                            if isinstance(inner_res, list):
                                results.extend(inner_res)
                            else:
                                results.append(inner_res)
            elif isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)
                    elif isinstance(item, str):
                        inner_res = self.extract(text=item, key=key)
                        if inner_res is not None:
                            if isinstance(inner_res, list):
                                results.extend(inner_res)
                            else:
                                results.append(inner_res)

        seen = set()
        final_results = []
        for r in results:
            if isinstance(r, str) and ':' in r and r.strip().startswith('{'):
                try:
                    if self.strict_level == 2:
                        import orjson
                        parsed_r = orjson.loads(r)
                    elif self.strict_level == 1:
                        import json
                        parsed_r = json.loads(r)
                    elif self.strict_level == 0:
                        import json5
                        parsed_r = json5.loads(r)
                    r = parsed_r
                except Exception:
                    pass

            h = str(r)
            if h not in seen:
                final_results.append(r)
                seen.add(h)
        return final_results[0] if final_results else final_results

__all__ = [
    "extract_nested_objects",
    "JSONScanner",
]

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

    # with open(r"", "r", encoding='utf-8') as f:
    #     text = f.read()

    print(extract_nested_objects(text=data, key="a")) # [{'d0': 14, 'd2': '15'}, 1]
    print(extract_nested_objects(text=data, key="_a")) # [4, 12, 22, 30]
    print(extract_nested_objects(text=data, key="c")) # [0, '3', {'_a': 4, '_b': '5'}]
    print(extract_nested_objects(text=data, key="e")) # [8, 18]
    print(extract_nested_objects(text=data, key="raw")) # []
    print(extract_nested_objects(text=data, key="key")) # []
    print(extract_nested_objects(text=data, key="deep")) # []
    print(extract_nested_objects(text=data, key="event")) # []
    print(extract_nested_objects(text=data, key="target")) # []
    # print(extract_nested_objects(text=text, key="emoji")) # []
    print("————————————————————————————extract_nested_objects_deep (base)————————————————————————————")
    jsonExtractor = JSONExtractor()
    jsonExtractor1 = JSONExtractor(strict_level=0)
    print(jsonExtractor.extract(text=data, key="a")) # [1, {'d0': 14, 'd2': '15'}]
    print(jsonExtractor.extract(text=data, key="_a")) # [4, 12, 22, 30]
    print(jsonExtractor.extract(text=data, key="c")) # [0, '3', {'_a': 4, '_b': '5'}]
    print(jsonExtractor1.extract(text=data, key="e")) # 8
    print(jsonExtractor.extract(text=data, key="raw")) # {"key": {"deep": "value"}}
    print(jsonExtractor.extract(text=data, key="key")) # {'deep': 'value'}
    print(jsonExtractor.extract(text=data, key="deep")) # value
    print(jsonExtractor.extract(text=data, key="event")) # ['click', 'scroll']
    print(jsonExtractor.extract(text=data, key="target")) # ['button', 'window']
    # print(jsonExtractor.extract(text=text, key="emoji")) # []
    print("————————————————————————————extract_nested_objects_deep (strong)————————————————————————————")
    jsonEScanner = JSONScanner()
    jsonEScanner1 = JSONScanner(strict_level=0)
    print(jsonEScanner.scan_text(text=data, key="a")) # [1, {'d0': 14, 'd2': '15'}]
    print(jsonEScanner.scan_text(text=data, key="_a")) # [4, 12, 22, 30]
    print(jsonEScanner.scan_text(text=data, key="c")) # [0, '3', {'_a': 4, '_b': '5'}]
    print(jsonEScanner1.scan_text(text=data, key="e")) # 8
    print(jsonEScanner.scan_text(text=data, key="raw")) # {"key": {"deep": "value"}}
    print(jsonEScanner.scan_text(text=data, key="key")) # {'deep': 'value'}
    print(jsonEScanner.scan_text(text=data, key="deep")) # value
    print(jsonEScanner.scan_text(text=data, key="event")) # ['click', 'scroll']
    print(jsonEScanner.scan_text(text=data, key="target")) # ['button', 'window']
    # print(jsonEScanner.scan_text(text=text, key="emoji")) # 😀