#!/usr/bin/env python3
from flask import Flask, request, jsonify
from flask_cors import CORS
from webscout import DuckDuckGoSearch, Meta, GitToolkit
import json
import re
import requests

app = Flask(__name__)
CORS(app)

@app.route('/search', methods=['POST'])
def search_web():
    """Use Webscout's DuckDuckGo search (no API key needed)"""
    data = request.json
    query = data.get('query', '')
    
    try:
        ddg = DuckDuckGoSearch()
        # Use the correct 'text' method
        results = ddg.text(query, max_results=5)
        
        # Format results for your app
        formatted_results = ""
        for r in results[:5]:
            if isinstance(r, dict):
                title = r.get('title', 'No title')
                body = r.get('body', '') or r.get('description', '')
                link = r.get('href', '')
                formatted_results += f"📌 {title}\n{body[:200]}...\n{link}\n\n"
            else:
                formatted_results += str(r) + "\n"
        
        return jsonify({"results": formatted_results or "No results found"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/gather-repo', methods=['POST'])
def gather_repo_info():
    """Gather repository information using GitAPI and search"""
    data = request.json
    owner = data.get('owner')
    repo = data.get('repo')
    
    try:
        git = GitToolkit()
        
        # Important files to check
        important_paths = [
            'README.md', 'package.json', 'requirements.txt', 'go.mod',
            'Cargo.toml', 'Gemfile', 'composer.json',
            '.env.example', 'config.js', 'config.py', 'config.json',
            'auth.js', 'auth.py', 'auth.go', 'routes/auth.js',
            'middleware/auth.js', 'app.js', 'index.js', 'main.py', 'main.go',
            '.gitignore', 'docker-compose.yml', 'Dockerfile',
            'secrets.yml', 'credentials.yml', 'database.yml'
        ]
        
        files_found = []
        for path in important_paths:
            try:
                content = git.get_file_content(owner, repo, path)
                if content and len(content) < 50000:  # Limit file size
                    files_found.append(f"=== {path} ===\n{content[:5000]}")
            except Exception as e:
                pass
        
        # Also search for repo info using correct 'text' method
        ddg = DuckDuckGoSearch()
        try:
            search_results = ddg.text(f"{owner} {repo} github", max_results=3)
            search_text = ""
            for r in search_results[:3]:
                if isinstance(r, dict):
                    title = r.get('title', '')
                    body = r.get('body', '') or r.get('description', '')
                    search_text += f"📌 {title}\n{body[:200]}...\n\n"
        except Exception as e:
            search_text = f"Search results unavailable: {str(e)}"
        
        # Try GitHub API as fallback
        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            api_response = requests.get(api_url)
            if api_response.status_code == 200:
                repo_data = api_response.json()
                github_info = f"\n📊 GitHub Stats:\n"
                github_info += f"   - Stars: {repo_data.get('stargazers_count', 0)}\n"
                github_info += f"   - Forks: {repo_data.get('forks_count', 0)}\n"
                github_info += f"   - Language: {repo_data.get('language', 'Unknown')}\n"
                github_info += f"   - Description: {repo_data.get('description', 'No description')}\n"
            else:
                github_info = ""
        except:
            github_info = ""
        
        # Combine everything
        repo_summary = f"Repository: {owner}/{repo}\n"
        repo_summary += "="*50 + "\n\n"
        repo_summary += github_info + "\n"
        repo_summary += "SEARCH RESULTS:\n" + search_text + "\n"
        repo_summary += "FILE CONTENTS:\n" + "\n".join(files_found) if files_found else "No files found"
        
        return jsonify({"gathered": repo_summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analyze', methods=['POST'])
def analyze_security():
    """Use Meta AI (free, no key) for security analysis"""
    data = request.json
    code_context = data.get('code', '')
    
    try:
        meta = Meta()
        
        prompt = f"""You are a senior application security engineer. Analyze this repository data and perform a comprehensive security audit:

{code_context[:50000]}

Check for ALL security issues and respond with ONLY valid JSON in this exact format:
{{
  "summary": "2-3 sentence executive summary of security posture",
  "score": <integer 0-100>,
  "vulnerabilities": [
    {{
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "title": "short title",
      "file": "filepath or null",
      "line": "line number or null",
      "description": "detailed description",
      "impact": "what attacker could do",
      "recommendation": "specific fix"
    }}
  ],
  "positives": ["good practice 1", "good practice 2"],
  "stats": {{"critical":0, "high":0, "medium":0, "low":0, "info":0}}
}}"""

        response = meta.chat(prompt)
        
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            # Validate it's proper JSON
            try:
                json.loads(json_match.group())
                return jsonify({"analysis": json_match.group()})
            except:
                return jsonify({"analysis": response})
        else:
            return jsonify({"analysis": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 Webscout backend starting on http://localhost:5000")
    print("✅ Available methods: text(), news(), videos(), images(), etc.")
    app.run(host='0.0.0.0', port=5000, debug=True)
