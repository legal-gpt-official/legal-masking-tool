# legal-masking-tool
Offline Japanese contract masking tool (GiNZA + Presidio)
# Legal Masking Tool

🛡️ Contract-focused masking tool for Japanese documents  
日本語契約書向け・完全オフライン型マスキングツール

---

## Overview

Legal Masking Tool is a Windows-based offline application designed to detect and mask sensitive information in Japanese contracts.

It uses:

- **GiNZA (spaCy-based Japanese NLP)**
- **Microsoft Presidio (entity detection and anonymization)**
- Rule-based custom detection logic

to identify entities such as:

- Company names
- Personal names
- Addresses
- Phone numbers
- Emails
- Contract numbers
- Dates
- Monetary amounts
- Custom-defined sensitive terms

All processing is performed locally.  
No document data is transmitted externally.

---

## Features

- 🔒 Fully offline processing (no API calls)
- 🧠 GiNZA-based Japanese NLP
- 🧠 Microsoft Presidio integration
- 📋 Contract-specific detection rules
- 👁️ Manual review before masking
- 📄 Supports `.docx`, `.txt`, and `.pdf`
- ⚡ Portable Windows executable (no installation required)

---

## System Requirements

- Windows 10 / 11
- Python 3.10+
- Approx. 300MB disk space (NLP models required)

---

## Installation (From Source)

```bash
git clone https://github.com/legal-gpt-official/legal-masking-tool.git
cd legal-masking-tool
pip install -r requirements.txt
python bootstrap.py
Build Executable

Example using PyInstaller:

pyinstaller main.spec


The built executable will be generated in the dist/ directory.

NLP Model Setup

GiNZA model must be installed separately:

python -m spacy download ja_ginza

License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

You are free to:

Use

Modify

Distribute

under the terms of AGPL-3.0.

If you distribute this software in binary or executable form,
you must also provide access to the complete corresponding source code,
as required by AGPLv3 Section 6.

The official source repository is:

https://github.com/legal-gpt-official/legal-masking-tool

See the LICENSE file for the full license text.

Trademark Notice

"Legal GPT" and "Legal Masking Tool" are trademarks of Legal GPT Editorial Department.

This license does not grant permission to use our trademarks,
service marks, or product names in modified versions
without prior written permission.

Unauthorized use of the Legal GPT name or logo in modified versions
is strictly prohibited.

Third-Party Components

This project includes open-source software:

GiNZA (Apache License 2.0)

spaCy (MIT License)

Microsoft Presidio (Apache License 2.0)

PyMuPDF (AGPL-3.0)

Python (PSF License)

See THIRD_PARTY_LICENSES.txt for detailed license information.

Disclaimer

This software is provided "AS IS", without warranty of any kind.

This tool is intended for professional review support purposes only.

The authors shall not be liable for any claim, damages,
or other liability arising from the use of this software.

Users must perform final manual verification
before disclosure or submission of documents.

Security

This tool operates entirely offline and does not transmit data externally.

If you discover a security vulnerability, please report it to:

contact@legal-gpt.com

Maintainer

Legal GPT Editorial Department
https://legal-gpt.com/
