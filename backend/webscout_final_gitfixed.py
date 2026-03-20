#!/usr/bin/env python3
from flask import Flask, request, jsonify
import base64
from flask_cors import CORS
from webscout import DuckDuckGoSearch, WiseCat
from webscout import GitToolkit
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
        results = ddg.text(query, max_results=5)
        
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
    """Gather repository information using GitToolkit"""
    data = request.json
    owner = data.get('owner')
    repo = data.get('repo')
    
    try:
        # Initialize repository
        git_repo = GitToolkit.Repository(owner, repo)
        
        # Get repo info
        repo_info = git_repo.get_info()
        
        # Get languages
        languages = git_repo.get_languages()
        
        # Get readme
        readme = git_repo.get_readme()
        
        files_found = []
        
        # Important files to check
        important_paths = [
            'package.json', 'requirements.txt', 'go.mod',
            'Cargo.toml', 'Gemfile', 'composer.json',
            '.env.example', 'config.js', 'config.py', 'config.json',
            'auth.js', 'auth.py', 'auth.go', 'routes/auth.js',
            'middleware/auth.js', 'app.js', 'index.js', 'main.py', 'main.go',
            '.gitignore', 'docker-compose.yml', 'Dockerfile',
            'secrets.yml', 'credentials.yml', 'database.yml'
        ]
        
        # Try to get important files
        for path in important_paths:
            try:
                content = git_repo.get_contents(path)
                if content and len(content) < 50000:
                    # Decode if base64 encoded
                    if isinstance(content, dict) and 'content' in content:
                        file_content = base64.b64decode(content['content']).decode('utf-8', errors='ignore')
                        files_found.append(f"=== {path} ===\n{file_content[:5000]}")
                    else:
                        files_found.append(f"=== {path} ===\n{str(content)[:5000]}")
            except Exception as e:
                pass
        
        # Format repo info
        github_info = f"\n📊 GitHub Stats:\n"
        github_info += f"   - Name: {repo_info.get('name', 'N/A')}\n"
        github_info += f"   - Description: {repo_info.get('description', 'No description')}\n"
        github_info += f"   - Stars: {repo_info.get('stargazers_count', 0)}\n"
        github_info += f"   - Forks: {repo_info.get('forks_count', 0)}\n"
        github_info += f"   - Language: {repo_info.get('language', 'Unknown')}\n"
        github_info += f"   - Languages: {', '.join(list(languages.keys())[:5])}\n"
        
        # Add README if available
        if readme:
            readme_content = readme.get('content', '')
            if readme_content:
                try:
                    readme_text = base64.b64decode(readme_content).decode('utf-8', errors='ignore')
                    files_found.insert(0, f"=== README.md ===\n{readme_text[:2000]}")
                except:
                    pass
        
        # Search for repo info using DuckDuckGo
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
            search_text = f"Search results unavailable: {str(e)}\n"
        
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
        ai = WiseCat()
        
        prompt = "You are a senior application security engineer. Analyze this repository data and perform a comprehensive security audit. Repository data: " + code_context[:50000] + " Respond with ONLY valid JSON: {summary, score (0-100), vulnerabilities: [{severity, title, file, line, description, impact, recommendation}], positives, stats: {critical, high, medium, low, info}}"

        response = ai.chat(prompt)
        
        # Clean and extract JSON from response
        try:
            response_clean = response.encode('utf-8', errors='ignore').decode('utf-8')
            fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_clean)
            if fence:
                json_str = fence.group(1).strip()
            else:
                brace = re.search(r'(\{[\s\S]*\})', response_clean)
                json_str = brace.group(1).strip() if brace else response_clean
            json.loads(json_str)
            return jsonify({"analysis": json_str})
        except Exception as parse_err:
            return jsonify({"analysis": response, "parse_error": str(parse_err)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 Webscout backend starting on http://localhost:5000")
    print("✅ Using GitToolkit.Repository correctly")
    app.run(host='0.0.0.0', port=5000, debug=True)
