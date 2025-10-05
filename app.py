import os
import json
from flask import Flask, request, render_template_string
import google.generativeai as genai
import markdown  # NEW: Import the markdown library

# --- 1. Initialize & Configure ---
app = Flask(__name__)
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-pro')
except KeyError:
    model = None

# --- 2. The System Prompt (Unchanged) ---
# MODIFIED: A much stricter system prompt based on user feedback.
SYSTEM_PROMPT = """
You are a literal and precise AI assistant. Your sole function is to help a Product Owner structure their raw input into a Jira ticket.

**Core Directives:**
1.  **Strictly Adhere to Context:** DO NOT assume, invent, or imagine any details, examples, possibilities, or edge cases not explicitly mentioned in the user's input. Your analysis must be a direct logical extension of the provided text only.
2.  **No Beautification:** The output must be plain text. Do not use markdown for styling like bolding (`**`), headers (`##`), or quotes (`>`). The only required formatting is the section titles.
3.  **Be Concise:** Do not use filler words or verbose explanations. Keep the output direct and of a reasonable length.
4.  **Handle Irrelevant Questions:** If the user responds with "NA" or "irrelevant" to a question, acknowledge it and do not ask about that topic again.

**Workflow:**
1.  **On First Input:** Receive the `User Story` and `Context`. Analyze ONLY this information to create a draft. Identify ambiguities WITHIN the provided text and formulate them as `clarifying_questions`.
2.  **On Subsequent Inputs:** Receive the user's answers. Integrate the new, factual information into the ticket. Refine the draft. If new ambiguities arise from the answers, ask new questions. If the ticket is sufficiently detailed based on the given information, return an empty list for `clarifying_questions`.

**Output Structure:**
Your response MUST be a valid JSON object with three keys: "ticket_draft", "clarifying_questions", and "open_questions".

- `ticket_draft`: A plain text string containing ONLY the following sections: `User Story`, `Context`, `Acceptance Criteria`.
- `clarifying_questions`: A list of strings for the PO to answer.
- `open_questions`: A list of strings identifying topics for developers to explore, based ONLY on ambiguities in the context.

**Example JSON Output:**
{
  "ticket_draft": "User Story\\nAs a user, I want to see detailed error messages.\\n\\nContext\\nThe current system shows a generic 'Failed' message. We need to display specific errors from the backend.\\n\\nAcceptance Criteria\\n- The system must display specific error messages from the backend instead of 'Failed'.",
  "clarifying_questions": [
    "What specific backend error messages should be displayed?",
    "Should there be a retry button for certain types of errors?"
  ],
  "open_questions": [
    "What are all the possible error categories we need to handle?",
    "How should the different errors be displayed in the UI (e.g., tooltip, table)?"
  ]
}
"""

# --- 3. HTML Template ---
# MODIFIED: Major changes to layout, styling, and forms.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>PRD Ticket Assistant</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 2em; }
        .container { display: flex; gap: 30px; }
        .interaction-pane { flex: 1; }
        .preview-pane { flex: 1.5; }
        .card { background: #fff; padding: 25px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 20px; }
        h1, h2, h3 { color: #172b4d; }
        h1 { text-align: center; margin-bottom: 30px; }
        label { font-weight: 600; font-size: 0.9em; color: #5e6c84; display: block; margin-top: 15px; margin-bottom: 5px; }
        input[type='text'], textarea { width: 98%; padding: 10px; border-radius: 4px; border: 1px solid #dfe1e6; font-size: 14px; }
        textarea { height: 250px; resize: vertical; }
        input[type='submit'] { width: 100%; padding: 12px; margin-top: 20px; border: none; background-color: #0052cc; color: white; font-size: 16px; font-weight: 600; border-radius: 4px; cursor: pointer; }
        input[type='submit']:hover { background-color: #0065ff; }
        /* NEW: Styles for the clean, sheet-like output */
        .sheet { background: #fff; padding: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); border: 1px solid #eee; min-height: 500px; }
        .sheet h2 { margin-top: 0; }
        .sheet blockquote { border-left: 3px solid #0052cc; margin-left: 0; padding-left: 1em; color: #42526e; }
        .sheet ul, .sheet ol { padding-left: 20px; }
        /* NEW: Styles for the interactive questions */
        .ai-questions { margin-top: 30px; background-color: #f0f8ff; padding: 20px; border-radius: 5px; }
        .error { color: #de350b; font-weight: bold; }
    </style>
</head>
<body>
    <h1>📄 PRD Ticket Assistant V2</h1>
    {% if api_key_error %} <p class="error">{{ api_key_error }}</p> {% endif %}
    <div class="container">
        <div class="interaction-pane">
            <div class="card">
                <h2>1. Initial Input</h2>
                <form method="post">
                    <label for="user_story">User Story</label>
                    <input type="text" id="user_story" name="user_story" value="{{ user_story or '' }}" required>
                    
                    <label for="context">Context & Brain Dump</label>
                    <textarea id="context" name="context">{{ context or '' }}</textarea>
                    
                    <input type="hidden" name="previous_context" value="{{ context }}">
                    {% for q in clarifying_questions %}
                        <input type="hidden" name="question_{{ loop.index0 }}" value="{{ q }}">
                    {% endfor %}

                    {% if clarifying_questions %}
                    <div class="ai-questions">
                        <h3>2. AI's Clarifying Questions</h3>
                        {% for q in clarifying_questions %}
                            <label for="answer_{{ loop.index0 }}">{{ q }}</label>
                            <input type="text" id="answer_{{ loop.index0 }}" name="answer_{{ loop.index0 }}" placeholder="Your answer here...">
                        {% endfor %}
                    </div>
                    {% endif %}
                    
                    <input type="submit" value="Submit & Refine">
                </form>
            </div>
        </div>
        <div class="preview-pane">
            <h2>Output Preview</h2>
            <div class="sheet">
                {% if preview_html %}
                    {{ preview_html | safe }}
                {% else %}
                    <p style="color: #5e6c84;">The ticket preview will appear here.</p>
                {% endif %}
            </div>
        </div>
    </div>
</body>
</html>
"""

# --- 4. The AI Logic Function ---
def get_ai_analysis(prompt):
    if not model: return {"error": "API Key not configured."}
    try:
        response = model.generate_content([SYSTEM_PROMPT, prompt])
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(cleaned_response)
    except Exception as e:
        return {"error": f"An error occurred: {e}"}

# --- 5. Main App Route ---
# MODIFIED: The logic is now more complex to handle the conversation loop.
@app.route('/', methods=['GET', 'POST'])
def index():
    if not model: return render_template_string(HTML_TEMPLATE, api_key_error="ERROR: GOOGLE_API_KEY is not set.")

    # Initialize variables
    view_data = {
        "user_story": "", "context": "", "preview_html": "",
        "clarifying_questions": [], "api_key_error": None
    }

    if request.method == 'POST':
        user_story = request.form['user_story']
        context = request.form['context']
        
        # Build the prompt for the AI
        prompt = f"User Story: {user_story}\n\nContext/Brain Dump:\n{context}"
        
        # NEW: Check for and append answers to previous questions
        answers_text = ""
        i = 0
        while f"question_{i}" in request.form:
            question = request.form[f"question_{i}"]
            answer = request.form[f"answer_{i}"]
            if answer: # Only include non-empty answers
                answers_text += f"\n\nQuestion: {question}\nAnswer: {answer}"
            i += 1
        
        if answers_text:
            prompt += "\n\n--- User's Answers to Previous Questions ---" + answers_text

        # Get analysis from the AI model
        analysis = get_ai_analysis(prompt)
        
        if "error" in analysis:
            view_data["preview_html"] = f"<p class='error'>Error: {analysis['error']}</p>"
        else:
            ticket_draft_md = analysis.get("ticket_draft", "")
            # NEW: Convert markdown to HTML before sending to template
            view_data["preview_html"] = markdown.markdown(ticket_draft_md)
            view_data["clarifying_questions"] = analysis.get("clarifying_questions", [])

        view_data["user_story"] = user_story
        view_data["context"] = context
        
    return render_template_string(HTML_TEMPLATE, **view_data)

# --- 6. Run the App ---
if __name__ == '__main__':
    app.run(debug=True)