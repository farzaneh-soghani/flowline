# <p align="left">
  <img src="static/img/FlowLine_icon.svg" width="45" height="45" align="left" style="margin-right: 20px; margin-top: 4px;" alt="FlowLine Logo">
  <span style="font-size: 26px; font-weight: bold;">FlowLine</span><br>
  <span style="font-size: 10px; color: #8b949e;">Applications in Flow</span>
  </p>

## Bewerbungsverwaltung im Überblick

## 🌐 Live Demo

[![Live Demo](https://img.shields.io/badge/Live-Deployed-brightgreen?logo=render)](https://farzaneh-soghani-flowline.onrender.com)

📱 **Unterwegs? KEIN Problem!** Responsiv für **Handy + Desktop** - deine Bewerbungen immer dabei! 🚀  
> **Im Handy oder Desktop direkt im Browser eingeben: [(https://farzaneh-soghani-flowline.onrender.com)](https://farzaneh-soghani-flowline.onrender.com)**   

## 🚀 Features

- ✅ Vollständiges **CRUD** (Create, Read, Update, Delete)
- 📝 **Notizen** pro Bewerbungen
- 📱 **Responsive Design** (max-width: 1000px, @media 768px)
- 💾 **Session Storage** (365 Tage persistent)
- 📈 **Live Statistics Dashboard** (`/stats`)
- ⏱️ **Automatisches Bewerbungserstellungsdatum** (DD.MM.YYYY)
- 🎨 **Clean Flexbox UI** + Mobile-First Design  

## 🏁 Quick Start

```bash
pip install -r requirements.txt
python app.py
```

→ Browser öffnet automatisch! 🎉

## 📸 Screenshots  

**Desktop Dashboard**  
![Desktop](screenshots/desktop.png)
  
  **Mobile Dashboard**  
![Mobile](screenshots/mobile.png)  
  
  **Statistics**  
![Stats](screenshots/stats.png)
  
  **Edit Form**  
![Edit](screenshots/edit.png)  
  
  **Notizen**  
![Notes](screenshots/notes.png)


## 📁 Projektstruktur

**Auflistung der Ordnerpfade**  
*(Automatisch generiert mit `tree /f` command)*  

```txt
C:.
│
├── app.py # Flask Backend + Bewerbungslogik
├── requirements.txt # Flask 3.0.3 + pytest 7.4.0 + gunicorn
├── Procfile # Render Deployment
├── pytest.ini # Test-Konfiguration
├── struktur.txt # Lokale Projektnotizen
│
├── .github/
│ └── workflows/
│ └── ci.yml # GitHub Actions CI/CD
│
├── templates/ # HTML/Jinja2 Templates
│ ├── index.html
│ ├── stats.html
│ ├── edit.html
│ └── notes.html
│
└── tests/
└── test_app.py # pytest Unit-Tests
```  

**💼 Made with ❤️ in Hamburg | [🔗 LinkedIn](https://www.linkedin.com/in/farzaneh-soghani/)**
