# 🚀 B2B Social Media Lead Scraper & AI Classifier

An automated, serverless pipeline designed to extract, enrich, and classify B2B leads from social media platforms. It leverages Python for data extraction and Google's Gemini AI to automatically score and segment profiles based on Ideal Customer Profile (ICP) criteria.

---

## 📌 Business Problem
Manual lead generation on social media is highly inefficient, time-consuming, and prone to human error. Sales teams often waste hours reviewing unqualified profiles instead of focusing on actual decision-makers.

## 💡 Solution
This project automates the entire prospecting workflow:
1. **Extraction:** Scrapes followers and active commenters from target B2B profiles.
2. **Enrichment:** Uses Regex to parse raw bio and link data, extracting emails and WhatsApp numbers.
3. **AI Classification:** Integrates with the **Gemini 2.0 Flash API** to read the unstructured profile data and return a strict JSON scoring the lead's B2B potential.
4. **Storage:** Automatically logs qualified leads into a Google Sheets CRM.

---

## 🏗️ Architecture & Tech Stack

- **Language:** Python 3
- **Data Extraction:** `instaloader`
- **AI & NLP:** Google Gemini API (`generativelanguage.googleapis.com`)
- **Data Destination:** Google Sheets API (`gspread`)
- **Orchestration / CI-CD:** GitHub Actions (Automated CRON jobs)
- **Security:** `dotenv` for environment variable management

---

## ⚙️ How It Works (Serverless Execution)

This script is designed to run autonomously in the cloud without local intervention. 
The `.github/workflows/scraper.yml` handles the CRON schedule, injecting the necessary secrets dynamically during runtime.

### Required Environment Variables (Secrets)
To run this pipeline, the following variables must be configured securely:
- `IG_USERNAME` & `IG_PASSWORD`
- `IG_SESSION` (Base64 encoded session cookies to bypass login blocks)
- `GEMINI_API_KEY`
- `SHEETS_ID`
- `GOOGLE_CREDENTIALS` (Service Account JSON)

---

## ✉️ Contact
Developed by **Daniel Felipe Dias do Amaral Galdino**  
[LinkedIn](https://linkedin.com/in/dfelipe-dias/) | [Email](mailto:dnfelipe27@gmail.com)
