"""Every sentence the shared pieces show. An app in another language replaces them with T.update({...})."""

T = {
    # Settings
    "settings": "Settings",
    "key_heading": "Groq API key",
    "key_explain": "The app uses Groq's free AI models. Your key is saved in this computer's keychain "
                   "and is only sent to Groq.",
    "key_saved_placeholder": "A key is saved - paste a new one to replace it",
    "get_key_link": "Get a free key at console.groq.com",
    "key_in_use": "A key from {where} is being used. A key saved here is used when that one is removed.",
    "where_env": "the GROQ_API_KEY environment variable",
    "where_dotenv": "the .env file",
    "remove_key": "Remove saved key",
    "close": "Close",
    "save_key": "Save key",
    "paste_key_first": "Paste your key first.",
    "checking_key": "Checking the key with Groq…",
    # Asking for a key
    "one_step": "One step first",
    "key_prompt": "{what} uses Groq's free AI. Add your Groq API key and you are ready to go.",
    "add_key": "Add API key",
    "get_free_key": "Get a free key",
    # General
    "working": "Working…",
    "delete": "Delete",
    "cannot_undo": "This cannot be undone.",
    # Errors from the AI
    "err_no_key": "Add your Groq API key first (Settings).",
    "err_auth": "Groq did not accept the API key. Check it in Settings.",
    "err_rate": "Groq's free limit was reached for the moment. Wait a minute and try again.",
    "err_timeout": "Groq took too long to answer. Try again.",
    "err_connection": "Could not reach Groq. Check your internet connection.",
    "err_status": "Groq returned an error ({code}). Try again in a moment.",
    "err_other": "Something went wrong: {error}",
    "err_unreadable": "The AI sent back an answer the app could not read. Try again.",
    "err_empty": "The AI sent back an empty answer. Try again.",
}
