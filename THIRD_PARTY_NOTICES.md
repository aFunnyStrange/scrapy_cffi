# Third-Party Notices

This project includes or adapts code from the following open-source projects.
Each third-party component retains its original license.

---

## 1. Scrapy

**Project:** [Scrapy](https://github.com/scrapy/scrapy)  
**License:** BSD 3-Clause License  
**Location in this project:** `scrapy_cffi/item/.base.py`

Portions of this project are derived from Scrapy’s `item.py` module, with necessary
adjustments for integration with scrapy_cffi’s asyncio-based architecture.

These adaptations preserve Scrapy’s original design for `Item` objects
while modifying data handling and dependency integration.

**Original copyright:**
Copyright (c) Scrapy developers.
All rights reserved.

---

## 2. blackboxprotobuf

**Project:** [blackboxprotobuf](https://github.com/nccgroup/blackboxprotobuf)  
**License:** MIT License  
**Location in this project:** `scrapy_cffi/utils/blackboxprotobuf/`

This directory contains a refactored subset of blackboxprotobuf (version 1.4.2),
retaining only the essential `encode_message` and `decode_message` APIs.
The source code has been simplified for internal use within scrapy_cffi.

**Original copyright:**
Copyright (c) 2018–2023 NCC Group Plc


---

## 3. pyblackboxprotobuf

**Project:** [pyblackboxprotobuf](https://github.com/aFunnyStrange/blackboxprotobuf)
**License:** MIT License
**Location:** Optional runtime dependency; not bundled in scrapy_cffi distributions.

When installed, scrapy_cffi may use this Rust-backed codec instead of its
bundled pure-Python fallback.

---

## 4. ppxxh

**Project:** [ppxxh](https://pypi.org/project/ppxxh/)
**License:** MIT License
**Location:** Runtime dependency; not bundled in scrapy_cffi distributions.

ppxxh provides the portable pure-Python XXH3 implementation used by the Bloom
platform fallback and to preserve Redis index compatibility across backends.

---

## 5. fastbloom-rs

**Project:** [fastbloom-rs](https://github.com/yankun1992/fastbloom)
**License:** Apache License 2.0
**Location:** Optional `bloom` runtime dependency; not bundled in scrapy_cffi distributions.

When installed, fastbloom-rs provides the Rust/PyO3 Bloom implementation behind
the framework-owned Bloom platform contract.

---

## 6. scrapy_cffi License

Unless otherwise noted, all other files in this repository are licensed under the
BSD 3-Clause License.

Copyright (c) 2025, aFunnyStrange
All rights reserved.
