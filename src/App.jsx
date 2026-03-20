import { useState, useCallback } from "react";

const SEV = {
  CRITICAL:{ color:'#ff3b3b', bg:'rgba(255,59,59,0.12)',  border:'rgba(255,59,59,0.3)',  icon:'💀' },
  HIGH:    { color:'#ff8c42', bg:'rgba(255,140,66,0.1)',  border:'rgba(255,140,66,0.3)', icon:'🔴' },
  MEDIUM:  { color:'#ffd166', bg:'rgba(255,209,102,0.1)',border:'rgba(255,209,102,0.3)',icon:'🟡' },
  LOW:     { color:'#06d6a0', bg:'rgba(6,214,160,0.1)',  border:'rgba(6,214,160,0.3)', icon:'🟢' },
  INFO:    { color:'#8ecae6', bg:'rgba(142,202,230,0.1)',border:'rgba(142,202,230,0.3)',icon:'ℹ️' },
};
const SEV_ORDER = ['CRITICAL','HIGH','MEDIUM','LOW','INFO'];

const CONF_STYLE = {
  '⚡ ULTRA-CONFIRMED':         { color:'#ff0000', bg:'rgba(255,0,0,0.18)' },
  'CONFIRMED BUG':               { color:'#ff3b3b', bg:'rgba(255,59,59,0.15)' },
  'LIKELY VULNERABLE':           { color:'#ff8c42', bg:'rgba(255,140,66,0.12)' },
  'POSSIBLE - Verify Manually':  { color:'#ffd166', bg:'rgba(255,209,102,0.1)' },
  'TEST/MOCK FILE':              { color:'#8ecae6', bg:'rgba(142,202,230,0.08)' },
  'INFO':                        { color:'#8ecae6', bg:'rgba(142,202,230,0.08)' },
};

function parseGitHubUrl(url) {
  const m = url.trim().match(/github\.com\/([^/\s]+)\/([^/\s?#]+)/);
  if (!m) return null;
  return { owner:m[1], repo:m[2].replace(/\.git$/,'') };
}
function extractJson(text) {
  const f = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (f) return f[1].trim();
  const b = text.match(/(\{[\s\S]*\})/);
  if (b) return b[1].trim();
  return text.trim();
}
async function gatherRepo(owner, repo) {
  const r = await fetch('http://localhost:5000/gather-repo',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({owner,repo})});
  const d = await r.json();
  if (d.error) throw new Error(d.error);
  return d;
}
async function analyzeRepo(files_dict, repo_info, code, repo_name) {
  const r = await fetch('http://localhost:5000/analyze',{
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({files_dict, repo_info, code, repo_name})});
  const d = await r.json();
  if (d.error) throw new Error(d.error);
  return d;
}

function ScoreRing({ score }) {
  const R = 52, circ = 2*Math.PI*R, filled = (score/100)*circ;
  const color = score>=80?'#06d6a0':score>=55?'#ffd166':score>=30?'#ff8c42':'#ff3b3b';
  return (
    <div style={{position:'relative',width:130,height:130,flexShrink:0}}>
      <svg width="130" height="130" style={{transform:'rotate(-90deg)'}}>
        <circle cx="65" cy="65" r={R} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="9"/>
        <circle cx="65" cy="65" r={R} fill="none" stroke={color} strokeWidth="9"
          strokeDasharray={`${filled} ${circ}`} strokeLinecap="round"
          style={{transition:'stroke-dasharray 1.4s cubic-bezier(.4,0,.2,1)',filter:`drop-shadow(0 0 10px ${color})`}}/>
      </svg>
      <div style={{position:'absolute',inset:0,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center'}}>
        <div style={{fontSize:30,fontWeight:800,color,fontFamily:'monospace',lineHeight:1}}>{score}</div>
        <div style={{fontSize:9,color:'rgba(255,255,255,0.35)',letterSpacing:2,marginTop:2}}>SCORE</div>
      </div>
    </div>
  );
}

function copyToClipboard(text) {
  navigator.clipboard?.writeText(text).catch(()=>{});
}

function VulnCard({ vuln, repoName }) {
  const [open,        setOpen]        = useState(false);
  const [showSandbox, setShowSandbox] = useState(false);
  const [showPoc,     setShowPoc]     = useState(false);
  const [copied,      setCopied]      = useState('');

  const cfg  = SEV[vuln.severity] || SEV.INFO;
  const conf = CONF_STYLE[vuln.confidence_label] || CONF_STYLE['INFO'];

  const isTestFile     = vuln.is_test_file;
  const isConfirmed    = ['CONFIRMED','ULTRA_CONFIRMED'].includes(vuln.confidence);
  const isUltra        = vuln.confidence === 'ULTRA_CONFIRMED';
  const isTaintTraced  = vuln.mitigations?.some(m => m.includes('TAINT') || m.includes('TRACE'));

  function doCopy(text, label) {
    copyToClipboard(text);
    setCopied(label);
    setTimeout(()=>setCopied(''),2000);
  }

  return (
    <div style={{
      background: open ? cfg.bg : 'rgba(255,255,255,0.025)',
      border:`1px solid ${open ? cfg.border : 'rgba(255,255,255,0.07)'}`,
      borderLeft:`5px solid ${isUltra ? '#ff0000' : isConfirmed ? cfg.color : 'rgba(255,255,255,0.15)'}`,
      borderRadius:10, marginBottom:8, transition:'all 0.18s',
      opacity: isTestFile ? 0.6 : 1,
      boxShadow: isUltra ? '0 0 18px rgba(255,0,0,0.2)' : 'none',
    }}>
      {/* ── Header ── */}
      <div onClick={()=>setOpen(o=>!o)} style={{cursor:'pointer',display:'flex',alignItems:'center',gap:10,padding:'12px 16px'}}>
        <span style={{fontSize:16}}>{cfg.icon}</span>
        <div style={{flex:1,minWidth:0}}>
          <div style={{display:'flex',alignItems:'center',gap:7,flexWrap:'wrap'}}>
            <span style={{fontSize:10,fontWeight:700,letterSpacing:1.5,padding:'2px 7px',borderRadius:4,
              background:cfg.bg,color:cfg.color,border:`1px solid ${cfg.border}`,fontFamily:'monospace'}}>
              {vuln.severity}
            </span>
            {vuln.confidence_label && vuln.confidence_label !== 'INFO' && (
              <span style={{fontSize:9,fontWeight:800,letterSpacing:1,padding:'2px 7px',borderRadius:4,
                background:conf.bg,color:conf.color,border:`1px solid ${conf.color}50`,fontFamily:'monospace'}}>
                {vuln.confidence_label}
              </span>
            )}
            {isTaintTraced && (
              <span style={{fontSize:9,fontWeight:800,padding:'2px 7px',borderRadius:4,
                background:'rgba(255,59,59,0.2)',color:'#ff3b3b',border:'1px solid rgba(255,59,59,0.4)',fontFamily:'monospace'}}>
                🔗 TAINT-TRACED
              </span>
            )}
            {isTestFile && (
              <span style={{fontSize:9,padding:'2px 6px',borderRadius:4,
                background:'rgba(255,255,255,0.06)',color:'rgba(255,255,255,0.35)',
                border:'1px solid rgba(255,255,255,0.1)'}}>TEST DATA</span>
            )}
            <span style={{fontSize:13,fontWeight:600,color:'rgba(255,255,255,0.9)'}}>{vuln.title}</span>
          </div>
          {(vuln.file||vuln.line) && (
            <div style={{fontSize:11,color:'rgba(255,255,255,0.28)',marginTop:3,fontFamily:'monospace',
              overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
              {vuln.file||''}{vuln.line ? ':'+vuln.line : ''}
            </div>
          )}
        </div>
        {vuln.payout && !isTestFile && (
          <div style={{fontSize:10,color:'#06d6a0',background:'rgba(6,214,160,0.1)',
            border:'1px solid rgba(6,214,160,0.25)',borderRadius:5,padding:'3px 8px',
            whiteSpace:'nowrap',flexShrink:0}}>
            💰 {vuln.payout}
          </div>
        )}
        <span style={{color:'rgba(255,255,255,0.25)',fontSize:11,
          transform:open?'rotate(180deg)':'none',transition:'0.2s',flexShrink:0}}>▼</span>
      </div>

      {/* ── Expanded body ── */}
      {open && (
        <div style={{padding:'0 16px 16px',borderTop:`1px solid ${cfg.border}`}}>
          <div style={{marginTop:12,display:'grid',gap:10}}>

            {/* Found snippet */}
            <div>
              <div style={{fontSize:10,fontWeight:700,color:cfg.color,letterSpacing:1.5,marginBottom:4}}>FOUND</div>
              <div style={{fontSize:11,fontFamily:'monospace',color:'rgba(255,255,255,0.75)',
                background:'rgba(0,0,0,0.35)',padding:'8px 10px',borderRadius:6,
                border:'1px solid rgba(255,255,255,0.08)',wordBreak:'break-all',lineHeight:1.7}}>
                {vuln.description}
              </div>
            </div>

            {/* Impact */}
            {vuln.impact && (
              <div>
                <div style={{fontSize:10,fontWeight:700,color:'#ff8c42',letterSpacing:1.5,marginBottom:4}}>IMPACT</div>
                <div style={{fontSize:12,color:'rgba(255,255,255,0.65)',lineHeight:1.6}}>{vuln.impact}</div>
              </div>
            )}

            {/* Recommendation */}
            {vuln.recommendation && (
              <div>
                <div style={{fontSize:10,fontWeight:700,color:'#06d6a0',letterSpacing:1.5,marginBottom:4}}>RECOMMENDATION</div>
                <div style={{fontSize:12,color:'rgba(255,255,255,0.65)',lineHeight:1.6}}>{vuln.recommendation}</div>
              </div>
            )}

            {/* Verdict */}
            {vuln.verdict && (
              <div>
                <div style={{fontSize:10,fontWeight:700,color:conf.color,letterSpacing:1.5,marginBottom:4}}>VERDICT</div>
                <div style={{fontSize:12,color:'rgba(255,255,255,0.65)',lineHeight:1.6}}>{vuln.verdict}</div>
              </div>
            )}

            {/* Chain of evidence */}
            {vuln.mitigations?.length > 0 && (
              <div style={{background:'rgba(255,209,102,0.06)',border:'1px solid rgba(255,209,102,0.2)',
                borderRadius:7,padding:'10px 12px'}}>
                <div style={{fontSize:10,fontWeight:700,color:'#ffd166',letterSpacing:1.5,marginBottom:6}}>
                  CHAIN OF EVIDENCE
                </div>
                {vuln.mitigations.map((m,i)=>(
                  <div key={i} style={{fontSize:11,color:'rgba(255,209,102,0.85)',lineHeight:1.7}}>↳ {m}</div>
                ))}
              </div>
            )}

            {/* Payout box */}
            {vuln.payout && !isTestFile && vuln.severity === 'CRITICAL' && isConfirmed && (
              <div style={{background:'rgba(6,214,160,0.07)',border:'1px solid rgba(6,214,160,0.25)',
                borderRadius:7,padding:'10px 12px',display:'flex',alignItems:'center',gap:10}}>
                <span style={{fontSize:20}}>💰</span>
                <div>
                  <div style={{fontSize:10,fontWeight:700,color:'#06d6a0',letterSpacing:1.5}}>ESTIMATED BOUNTY RANGE</div>
                  <div style={{fontSize:13,fontWeight:700,color:'#06d6a0',marginTop:2}}>{vuln.payout}</div>
                  <div style={{fontSize:10,color:'rgba(6,214,160,0.5)',marginTop:2}}>Verify exploitability before submitting. Reproduce first.</div>
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:4}}>
              {vuln.repro_steps?.length > 0 && (
                <button onClick={e=>{e.stopPropagation();setShowSandbox(s=>!s)}} style={{
                  background: showSandbox ? 'rgba(255,59,59,0.3)' : 'rgba(255,59,59,0.15)',
                  color:'#ff8c42', border:'1px solid rgba(255,59,59,0.35)',
                  padding:'6px 14px', borderRadius:6, cursor:'pointer', fontSize:11, fontWeight:600}}>
                  {showSandbox ? '✕ Close Exploit Guide' : '🚀 Exploit Workflow'}
                </button>
              )}
              {vuln.poc_markdown && (
                <button onClick={e=>{e.stopPropagation();setShowPoc(s=>!s)}} style={{
                  background: showPoc ? 'rgba(66,133,244,0.3)' : 'rgba(66,133,244,0.1)',
                  color:'#4285f4', border:'1px solid rgba(66,133,244,0.3)',
                  padding:'6px 14px', borderRadius:6, cursor:'pointer', fontSize:11, fontWeight:600}}>
                  {showPoc ? '✕ Close Report' : '📋 HackerOne Report'}
                </button>
              )}
            </div>

            {/* Exploit Sandbox */}
            {showSandbox && vuln.repro_steps?.length > 0 && (
              <div style={{background:'#0d1117',border:'1px solid rgba(255,59,59,0.3)',borderRadius:8,padding:'14px 16px'}}>
                <div style={{fontSize:11,fontWeight:700,color:'#ff3b3b',letterSpacing:1.5,marginBottom:10}}>
                  🔥 EXPLOIT REPRODUCTION WORKFLOW
                </div>
                <div style={{fontSize:10,color:'rgba(255,255,255,0.35)',marginBottom:10}}>
                  Follow these steps to reproduce and prove the vulnerability:
                </div>
                <ol style={{margin:0,padding:'0 0 0 18px'}}>
                  {vuln.repro_steps.map((step,i)=>(
                    <li key={i} style={{fontSize:12,color:'rgba(255,255,255,0.75)',lineHeight:1.8,marginBottom:4,
                      fontFamily: step.startsWith('Phase') ? 'system-ui' : 'monospace',
                      color: step.startsWith('Phase') ? '#ffd166' : 'rgba(255,255,255,0.65)'}}>
                      {step}
                    </li>
                  ))}
                </ol>
                {vuln.sandbox_curl && (
                  <div style={{marginTop:14}}>
                    <div style={{fontSize:10,fontWeight:700,color:'#06d6a0',letterSpacing:1.5,marginBottom:6}}>
                      TEST COMMAND
                    </div>
                    <div style={{background:'#000',padding:'10px 12px',borderRadius:6,
                      border:'1px solid rgba(255,255,255,0.08)',display:'flex',alignItems:'flex-start',gap:10}}>
                      <span style={{color:'#06d6a0',fontFamily:'monospace',fontSize:12,flexShrink:0}}>$</span>
                      <code style={{fontSize:11,color:'rgba(255,255,255,0.8)',fontFamily:'monospace',
                        wordBreak:'break-all',flex:1,lineHeight:1.6}}>{vuln.sandbox_curl}</code>
                      <button onClick={()=>doCopy(vuln.sandbox_curl,'curl')} style={{
                        background:'rgba(255,255,255,0.08)',border:'1px solid rgba(255,255,255,0.12)',
                        color: copied==='curl' ? '#06d6a0' : 'rgba(255,255,255,0.5)',
                        padding:'3px 8px',borderRadius:4,cursor:'pointer',fontSize:10,flexShrink:0}}>
                        {copied==='curl' ? '✓' : 'Copy'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* HackerOne PoC Report */}
            {showPoc && vuln.poc_markdown && (
              <div style={{background:'#0d1117',border:'1px solid rgba(66,133,244,0.3)',borderRadius:8,padding:'14px 16px'}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:10}}>
                  <div style={{fontSize:11,fontWeight:700,color:'#4285f4',letterSpacing:1.5}}>
                    📋 HACKERONE-READY REPORT
                  </div>
                  <button onClick={()=>doCopy(vuln.poc_markdown,'report')} style={{
                    background:'rgba(66,133,244,0.15)',border:'1px solid rgba(66,133,244,0.3)',
                    color: copied==='report' ? '#06d6a0' : '#4285f4',
                    padding:'4px 12px',borderRadius:4,cursor:'pointer',fontSize:10,fontWeight:600}}>
                    {copied==='report' ? '✓ Copied!' : '📋 Copy Markdown'}
                  </button>
                </div>
                <pre style={{fontSize:11,color:'rgba(255,255,255,0.65)',fontFamily:'monospace',
                  whiteSpace:'pre-wrap',lineHeight:1.7,margin:0,
                  maxHeight:400,overflowY:'auto',padding:'4px 0'}}>
                  {vuln.poc_markdown}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DepMapPanel({ depMap }) {
  if (!depMap) return null;
  const dirty     = depMap.dirty_files     || [];
  const dangerous = depMap.dangerous_files || [];
  if (!dirty.length && !dangerous.length) return null;

  return (
    <div style={{background:'rgba(255,255,255,0.02)',border:'1px solid rgba(255,255,255,0.06)',
      borderRadius:10,padding:'14px 16px',marginBottom:14}}>
      <div style={{fontSize:10,fontWeight:700,color:'rgba(255,255,255,0.35)',letterSpacing:1.5,marginBottom:12}}>
        DEPENDENCY MAP — FILES AT RISK
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
        <div>
          <div style={{fontSize:10,color:'#ffd166',fontWeight:600,marginBottom:6}}>
            🔴 DIRTY (User Input Sources)
          </div>
          {dirty.map(([path, count],i)=>(
            <div key={i} style={{display:'flex',justifyContent:'space-between',alignItems:'center',
              fontSize:10,fontFamily:'monospace',color:'rgba(255,255,255,0.5)',marginBottom:4,gap:8}}>
              <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>
                {path.split('/').slice(-2).join('/')}
              </span>
              <span style={{color:'#ffd166',flexShrink:0}}>{count} src</span>
            </div>
          ))}
        </div>
        <div>
          <div style={{fontSize:10,color:'#ff8c42',fontWeight:600,marginBottom:6}}>
            ⚡ DANGEROUS (Sink Functions)
          </div>
          {dangerous.map(([path, count],i)=>(
            <div key={i} style={{display:'flex',justifyContent:'space-between',alignItems:'center',
              fontSize:10,fontFamily:'monospace',color:'rgba(255,255,255,0.5)',marginBottom:4,gap:8}}>
              <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>
                {path.split('/').slice(-2).join('/')}
              </span>
              <span style={{color:'#ff8c42',flexShrink:0}}>{count} sink</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [url,        setUrl]        = useState('');
  const [logs,       setLogs]       = useState([]);
  const [progress,   setProgress]   = useState(0);
  const [loading,    setLoading]    = useState(false);
  const [report,     setReport]     = useState(null);
  const [repoName,   setRepoName]   = useState('');
  const [filter,     setFilter]     = useState('ALL');
  const [confFilter, setConfFilter] = useState('ALL');
  const [error,      setError]      = useState('');

  const addLog = (msg, prog) => {
    setLogs(l=>[...l,msg]);
    if (prog !== undefined) setProgress(prog);
  };

  const audit = useCallback(async () => {
    const parsed = parseGitHubUrl(url);
    if (!parsed) { setError('Enter a valid GitHub URL'); return; }
    setLoading(true); setReport(null); setError('');
    setLogs([]); setProgress(0); setFilter('ALL'); setConfFilter('ALL');
    const rn = parsed.owner + '/' + parsed.repo;
    setRepoName(rn);
    try {
      addLog('Fetching repository file tree (tests excluded)...', 8);
      const gathered = await gatherRepo(parsed.owner, parsed.repo);
      const fc = Object.keys(gathered.files_dict||{}).length;
      addLog('Fetched ' + fc + ' source files. Building taint map...', 25);
      addLog('Tracing user-controlled data flows across files...', 45);
      addLog('Following variables from source → sink (cross-line)...', 60);
      addLog('Logic flow validation — checking ownership & auth guards...', 72);
      addLog('Cross-referencing sinks with compensating controls...', 83);
      const analysisRaw = await analyzeRepo(gathered.files_dict||{}, gathered.repo_info||{}, gathered.gathered||'', rn);
      addLog('Generating exploit workflows and PoC reports...', 93);
      const result = analysisRaw;
      setReport(result);
      setProgress(100);
      const confirmed = (result.vulnerabilities||[]).filter(v=>['CONFIRMED','ULTRA_CONFIRMED'].includes(v.confidence)).length;
      const ultra     = (result.vulnerabilities||[]).filter(v=>v.confidence==='ULTRA_CONFIRMED').length;
      const tainted   = (result.vulnerabilities||[]).filter(v=>v.mitigations?.some(m=>m.includes('TAINT')||m.includes('TRACE'))).length;
      addLog(`Complete — ${result.vulnerabilities?.length||0} findings (${ultra} ULTRA, ${confirmed} confirmed, ${tainted} taint-traced)`, 100);
    } catch(err) {
      setError(err.message);
      addLog('Error: ' + err.message);
    } finally {
      setLoading(false);
    }
  }, [url]);

  const allVulns = report?.vulnerabilities || [];
  const vulns = allVulns
    .filter(v => filter==='ALL' || v.severity===filter)
    .filter(v => confFilter==='ALL' ||
      (confFilter==='ULTRA' && v.confidence==='ULTRA_CONFIRMED') ||
      (confFilter==='CONFIRMED' && ['CONFIRMED','ULTRA_CONFIRMED'].includes(v.confidence)) ||
      (confFilter==='LIKELY' && v.confidence==='LIKELY') ||
      (confFilter==='POSSIBLE' && v.confidence==='POSSIBLE'))
    .sort((a,b)=>{
      const sOrd = ['CRITICAL','HIGH','MEDIUM','LOW','INFO'];
      const cOrd = {'ULTRA_CONFIRMED':0,'CONFIRMED':1,'LIKELY':2,'POSSIBLE':3,'INFORMATIONAL':4};
      if (a.severity !== b.severity) return sOrd.indexOf(a.severity) - sOrd.indexOf(b.severity);
      return (cOrd[a.confidence]||5) - (cOrd[b.confidence]||5);
    });

  const ultraCount     = allVulns.filter(v=>v.confidence==='ULTRA_CONFIRMED').length;
  const confirmedCount = allVulns.filter(v=>['CONFIRMED','ULTRA_CONFIRMED'].includes(v.confidence)).length;
  const taintCount     = allVulns.filter(v=>v.mitigations?.some(m=>m.includes('TAINT')||m.includes('TRACE'))).length;

  return (
    <div style={{minHeight:'100vh',background:'#08090f',color:'#dde1ed',fontFamily:'system-ui,sans-serif',
      backgroundImage:'radial-gradient(ellipse 60% 40% at 10% 0%,rgba(255,59,59,0.07) 0%,transparent 70%)'}}>

      {/* Nav */}
      <div style={{borderBottom:'1px solid rgba(255,255,255,0.07)',padding:'14px 24px',display:'flex',alignItems:'center',gap:10}}>
        <div style={{width:30,height:30,borderRadius:7,background:'rgba(255,59,59,0.15)',border:'1px solid rgba(255,59,59,0.25)',
          display:'flex',alignItems:'center',justifyContent:'center',fontSize:15}}>🛡️</div>
        <span style={{fontSize:14,fontWeight:700}}>RepoAudit</span>
        <span style={{fontSize:9,color:'rgba(255,255,255,0.25)',letterSpacing:2}}>MEGA ULTRA ULTIMATE</span>
        <div style={{marginLeft:'auto',display:'flex',alignItems:'center',gap:5}}>
          <div style={{width:6,height:6,borderRadius:'50%',background:'#ff3b3b',boxShadow:'0 0 6px #ff3b3b'}}/>
        </div>
      </div>

      <div style={{maxWidth:900,margin:'0 auto',padding:'32px 18px'}}>
        <h1 style={{fontSize:24,fontWeight:700,letterSpacing:-0.5,margin:'0 0 4px'}}>GitHub Security Audit</h1>
        <p style={{fontSize:12,color:'rgba(255,255,255,0.3)',margin:'0 0 10px'}}>
          Cross-file taint tracing · Variable follower · Logic flow validation · Exploit factory · HackerOne reports
        </p>
        <div style={{display:'flex',gap:8,marginBottom:20,flexWrap:'wrap'}}>
          {['Cross-line taint trace','Variable follower','ULTRA-CONFIRMED logic','Exploit workflows','PoC report generator','Dependency map'].map(t=>(
            <span key={t} style={{fontSize:10,color:'#06d6a0',background:'rgba(6,214,160,0.08)',
              border:'1px solid rgba(6,214,160,0.2)',borderRadius:4,padding:'2px 8px'}}>✓ {t}</span>
          ))}
        </div>

        {/* Input */}
        <div style={{display:'flex',gap:8,marginBottom:16}}>
          <input value={url} onChange={e=>{setUrl(e.target.value);setError('');}}
            onKeyDown={e=>e.key==='Enter'&&!loading&&audit()}
            placeholder="https://github.com/owner/repository"
            style={{flex:1,padding:'12px 14px',background:'rgba(255,255,255,0.05)',
              border:'1px solid rgba(255,255,255,0.1)',borderRadius:9,color:'#dde1ed',
              fontSize:13,fontFamily:'monospace',outline:'none'}}/>
          <button onClick={audit} disabled={loading||!url.trim()} style={{
            padding:'12px 22px',borderRadius:9,border:'none',fontWeight:600,fontSize:13,
            cursor:loading||!url.trim()?'not-allowed':'pointer',whiteSpace:'nowrap',
            background:loading?'rgba(255,59,59,0.25)':'rgba(255,59,59,0.9)',
            color:loading?'rgba(255,255,255,0.4)':'#fff',
            boxShadow:loading?'none':'0 0 18px rgba(255,59,59,0.35)',transition:'all 0.2s'}}>
            {loading ? 'Scanning…' : 'Run Audit →'}
          </button>
        </div>

        {error && (
          <div style={{fontSize:13,color:'#ff3b3b',background:'rgba(255,59,59,0.08)',
            border:'1px solid rgba(255,59,59,0.2)',borderRadius:8,padding:'10px 14px',marginBottom:14}}>
            ⚠ {error}
          </div>
        )}

        {/* Live log */}
        {loading && (
          <div style={{marginBottom:24,background:'rgba(255,255,255,0.02)',border:'1px solid rgba(255,255,255,0.06)',borderRadius:10,padding:'14px 16px'}}>
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:8}}>
              <span style={{fontSize:10,color:'rgba(255,255,255,0.3)',letterSpacing:2}}>LIVE LOG</span>
              <span style={{fontSize:10,color:'#ff8c42',fontWeight:600}}>{progress}%</span>
            </div>
            <div style={{height:2,background:'rgba(255,255,255,0.05)',borderRadius:1,marginBottom:12,overflow:'hidden'}}>
              <div style={{height:'100%',width:`${progress}%`,background:'linear-gradient(90deg,#ff3b3b,#ff8c42)',transition:'width 0.5s ease'}}/>
            </div>
            {logs.map((l,i)=>(
              <div key={i} style={{fontSize:11,fontFamily:'monospace',marginBottom:3,
                color:i===logs.length-1?'rgba(255,255,255,0.6)':'rgba(255,255,255,0.2)'}}>
                {i===logs.length-1?'▶ ':'  '}{l}
              </div>
            ))}
          </div>
        )}

        {/* Report */}
        {report && !loading && (
          <div>
            {/* Score card */}
            <div style={{background:'rgba(255,255,255,0.03)',border:'1px solid rgba(255,255,255,0.08)',
              borderRadius:12,padding:'20px 22px',marginBottom:14,
              display:'flex',gap:22,alignItems:'center',flexWrap:'wrap'}}>
              <ScoreRing score={report.score??0}/>
              <div style={{flex:1,minWidth:200}}>
                <div style={{fontSize:15,fontWeight:700,fontFamily:'monospace',marginBottom:8}}>{repoName}</div>
                <p style={{fontSize:13,color:'rgba(255,255,255,0.5)',lineHeight:1.65,margin:'0 0 10px'}}>{report.summary}</p>
                <div style={{display:'flex',gap:10,flexWrap:'wrap',marginBottom:8}}>
                  {SEV_ORDER.map(s=>{
                    const cnt = report.stats?.[s.toLowerCase()]||0;
                    if(!cnt) return null;
                    return (
                      <div key={s} style={{display:'flex',alignItems:'center',gap:5}}>
                        <div style={{width:7,height:7,borderRadius:'50%',background:SEV[s].color,boxShadow:`0 0 4px ${SEV[s].color}`}}/>
                        <span style={{fontSize:12,color:'rgba(255,255,255,0.45)'}}>
                          <span style={{color:SEV[s].color,fontWeight:700}}>{cnt}</span> {s.toLowerCase()}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
                  {ultraCount > 0 && (
                    <span style={{fontSize:10,color:'#ff0000',background:'rgba(255,0,0,0.12)',
                      border:'1px solid rgba(255,0,0,0.3)',borderRadius:4,padding:'2px 8px',fontWeight:700}}>
                      ⚡ {ultraCount} ULTRA-CONFIRMED
                    </span>
                  )}
                  {confirmedCount > 0 && (
                    <span style={{fontSize:10,color:'#ff3b3b',background:'rgba(255,59,59,0.1)',
                      border:'1px solid rgba(255,59,59,0.25)',borderRadius:4,padding:'2px 8px'}}>
                      {confirmedCount} CONFIRMED
                    </span>
                  )}
                  {taintCount > 0 && (
                    <span style={{fontSize:10,color:'#ff8c42',background:'rgba(255,140,66,0.1)',
                      border:'1px solid rgba(255,140,66,0.25)',borderRadius:4,padding:'2px 8px'}}>
                      🔗 {taintCount} TAINT-TRACED
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Security architecture */}
            {report.intel && (
              <div style={{background:'rgba(255,255,255,0.02)',border:'1px solid rgba(255,255,255,0.06)',
                borderRadius:10,padding:'12px 16px',marginBottom:14}}>
                <div style={{fontSize:10,fontWeight:700,color:'rgba(255,255,255,0.35)',letterSpacing:1.5,marginBottom:8}}>
                  SECURITY ARCHITECTURE DETECTED
                </div>
                <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
                  {[
                    ['ORM / Safe Queries',    report.intel.has_orm],
                    ['CSRF Protection',       report.intel.has_csrf],
                    ['Auth Middleware',        report.intel.has_auth_middleware],
                    ['Input Validation',      report.intel.has_input_validation],
                    ['Rate Limiting',         report.intel.has_rate_limit],
                    ['Ownership Checks',      report.intel.has_ownership_check],
                  ].map(([label,val])=>(
                    <span key={label} style={{fontSize:10,padding:'3px 8px',borderRadius:4,
                      background:val?'rgba(6,214,160,0.1)':'rgba(255,59,59,0.08)',
                      color:val?'#06d6a0':'rgba(255,59,59,0.6)',
                      border:`1px solid ${val?'rgba(6,214,160,0.2)':'rgba(255,59,59,0.15)'}`}}>
                      {val?'✓':'✗'} {label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Dependency map */}
            <DepMapPanel depMap={report.dep_map}/>

            {/* Findings */}
            {allVulns.length > 0 && (
              <>
                <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
                  marginBottom:10,flexWrap:'wrap',gap:8}}>
                  <span style={{fontSize:13,fontWeight:600,color:'rgba(255,255,255,0.6)'}}>
                    Findings ({allVulns.length})
                  </span>
                  <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                    {['ALL',...SEV_ORDER.filter(s=>report.stats?.[s.toLowerCase()])].map(f=>(
                      <button key={f} onClick={e=>{e.stopPropagation();setFilter(f)}} style={{
                        padding:'3px 10px',borderRadius:6,fontSize:11,fontWeight:600,cursor:'pointer',
                        background:filter===f?(SEV[f]?.bg||'rgba(255,255,255,0.1)'):'transparent',
                        color:filter===f?(SEV[f]?.color||'#fff'):'rgba(255,255,255,0.28)',
                        border:`1px solid ${filter===f?(SEV[f]?.border||'rgba(255,255,255,0.2)'):'rgba(255,255,255,0.08)'}`}}>
                        {f}{f!=='ALL'&&` (${report.stats[f.toLowerCase()]})`}
                      </button>
                    ))}
                    <div style={{width:1,background:'rgba(255,255,255,0.1)',margin:'0 4px'}}/>
                    {[['ALL','All'],['ULTRA','⚡ Ultra'],['CONFIRMED','Confirmed'],['LIKELY','Likely'],['POSSIBLE','Possible']].map(([val,label])=>(
                      <button key={val} onClick={e=>{e.stopPropagation();setConfFilter(val)}} style={{
                        padding:'3px 10px',borderRadius:6,fontSize:10,fontWeight:600,cursor:'pointer',
                        background:confFilter===val?'rgba(255,255,255,0.08)':'transparent',
                        color:confFilter===val?'#fff':'rgba(255,255,255,0.28)',
                        border:`1px solid ${confFilter===val?'rgba(255,255,255,0.2)':'rgba(255,255,255,0.08)'}`}}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {vulns.map((v,i)=><VulnCard key={i} vuln={v} repoName={repoName}/>)}
                {vulns.length===0 && (
                  <div style={{textAlign:'center',padding:'30px',color:'rgba(255,255,255,0.2)',fontSize:13}}>
                    No findings match selected filters
                  </div>
                )}
              </>
            )}

            {/* Positives */}
            {report.positives?.length > 0 && (
              <div style={{background:'rgba(6,214,160,0.05)',border:'1px solid rgba(6,214,160,0.15)',
                borderRadius:10,padding:'16px 18px',marginTop:14}}>
                <div style={{fontSize:11,fontWeight:700,color:'#06d6a0',letterSpacing:1.5,marginBottom:8}}>
                  ✓ SECURITY CONTROLS DETECTED
                </div>
                <ul style={{margin:0,padding:'0 0 0 16px'}}>
                  {report.positives.map((p,i)=>(
                    <li key={i} style={{fontSize:13,color:'rgba(255,255,255,0.55)',lineHeight:1.7}}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {!loading&&!report&&!error&&(
          <div style={{textAlign:'center',padding:'60px 0',color:'rgba(255,255,255,0.12)'}}>
            <div style={{fontSize:44,marginBottom:12}}>🛡️</div>
            <div style={{fontSize:13}}>
              Paste a GitHub URL and press{' '}
              <strong style={{color:'rgba(255,255,255,0.2)'}}>Run Audit</strong>
            </div>
            <div style={{fontSize:11,marginTop:6,color:'rgba(255,255,255,0.08)'}}>
              Cross-file taint tracing · Variable follower · Logic flow validation ·
              ULTRA-CONFIRMED bugs · Exploit workflows · HackerOne PoC reports
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
