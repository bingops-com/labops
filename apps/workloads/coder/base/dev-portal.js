'use strict';
const $ = id => document.getElementById(id);
const state = { data: null, query: '', project: '', starredOnly: false, stale: false, busy: false, authenticated: false };
let favorites = new Set(), toastTimer;
try { const saved = JSON.parse(localStorage.getItem('dev.favorites.v1')); if (Array.isArray(saved)) favorites = new Set(saved.filter(p => Number.isInteger(p) && p >= 1024 && p <= 65535)); } catch {}
const systemDark = matchMedia('(prefers-color-scheme: dark)');
let theme = 'auto';
try { const saved = localStorage.getItem('dev.theme'); if (['auto','light','dark'].includes(saved)) theme = saved; } catch {}
function applyTheme() { document.documentElement.dataset.theme = theme === 'auto' ? (systemDark.matches ? 'dark' : 'light') : theme; $('theme').title = `Thème : ${theme === 'auto' ? 'automatique' : theme === 'dark' ? 'sombre' : 'clair'}`; }
$('theme').onclick = () => { theme = theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto'; try { localStorage.setItem('dev.theme', theme); } catch {} applyTheme(); };
systemDark.addEventListener('change', applyTheme); applyTheme();
function icon(name) { const svg = document.createElementNS('http://www.w3.org/2000/svg','svg'); const use = document.createElementNS(svg.namespaceURI,'use'); use.setAttribute('href',`#i-${name}`); svg.append(use); svg.setAttribute('aria-hidden','true'); return svg; }
function node(tag, className, text) { const element = document.createElement(tag); if (className) element.className = className; if (text !== undefined) element.textContent = text; return element; }
function toast(message) { clearTimeout(toastTimer); $('toast').textContent = message; $('toast').hidden = false; toastTimer = setTimeout(() => $('toast').hidden = true, 2400); }
async function copy(text) { try { await navigator.clipboard.writeText(text); toast('Adresse copiée'); } catch { toast('Copie indisponible : ouvrez le lien pour récupérer son adresse.'); } }
function appUrl(port) { return `https://${port}.dev.lab.bingo/`; }
function favorite(port) { favorites.has(port) ? favorites.delete(port) : favorites.add(port); try { localStorage.setItem('dev.favorites.v1', JSON.stringify([...favorites])); } catch {} render(); }
function portCard(port) {
  const card = node('article','port-card'); card.dataset.port = port.port;
  const head = node('div','port-card-head');
  const badge = node('span','project-badge',port.project.slice(0,2).toUpperCase()); badge.setAttribute('aria-hidden','true');
  const status = node('span',`port-status${state.stale || port.status === 'warning' ? ' warning' : ''}`);
  const dot = node('i',`dot${state.stale || port.status === 'warning' ? ' warning' : ''}`); dot.setAttribute('aria-hidden','true');
  status.append(dot, document.createTextNode(state.stale ? 'À vérifier' : port.status === 'warning' ? `HTTP ${port.http_status}` : 'Disponible'));
  const pin = node('button','star-button'); pin.type = 'button'; pin.setAttribute('aria-label',`${favorites.has(port.port) ? 'Retirer' : 'Ajouter'} ${port.project} ${port.port} ${favorites.has(port.port) ? 'des' : 'aux'} favoris`); pin.setAttribute('aria-pressed',String(favorites.has(port.port))); pin.append(icon('star')); pin.onclick = () => favorite(port.port);
  head.append(badge,status,pin);
  const body = node('div','port-card-content'); body.append(node('h3','',port.project),node('span','runtime',`${port.runtime} · HTTP`));
  const address = node('div','port-address'); address.append(node('strong','',String(port.port)),node('span','','.dev.lab.bingo'));
  const actions = node('div','port-card-actions'); const open = node('a','button','Ouvrir'); open.href = appUrl(port.port); open.target = '_blank'; open.rel = 'noopener'; open.setAttribute('aria-label',`Ouvrir ${port.project}, port ${port.port}`); open.append(icon('arrow'));
  const clip = node('button','icon-button'); clip.type='button'; clip.setAttribute('aria-label',`Copier l’adresse du port ${port.port}`); clip.append(icon('copy')); clip.onclick = () => copy(appUrl(port.port)); actions.append(open,clip); body.append(address,actions); card.append(head,body); return card;
}
function renderProjects() {
  const projects = state.data?.projects ?? [];
  $('project-count').textContent = state.authenticated ? projects.length : '—';
  if (!projects.length) { $('project-nav').replaceChildren(node('p','sidebar-empty',state.authenticated ? 'Aucun projet disponible.' : 'Connectez-vous pour voir vos projets.')); return; }
  const all = node('button',`project-button${!state.project ? ' selected' : ''}`); all.type='button'; all.append(icon('folder'),node('span','','Tous les projets')); all.onclick = () => { state.project=''; render(); };
  const buttons = projects.map(project => {
    const button = node('button',`project-button${state.project === project.name ? ' selected' : ''}`); button.type='button'; button.setAttribute('aria-pressed',String(state.project === project.name)); button.append(icon('folder'),node('span','',project.name));
    if (project.ports.length) button.append(node('small','',project.ports.length));
    button.onclick = () => { state.project=state.project === project.name ? '' : project.name; render(); $('servers-title').scrollIntoView({block:'nearest'}); }; return button;
  }); $('project-nav').replaceChildren(all,...buttons);
}
function render() {
  const ports = state.data?.ports ?? [];
  const filtered = ports.filter(port => (!state.starredOnly || favorites.has(port.port)) && (!state.project || port.project === state.project) && `${port.project} ${port.port} ${port.runtime}`.toLowerCase().includes(state.query.toLowerCase().trim())).sort((a,b) => Number(favorites.has(b.port))-Number(favorites.has(a.port)) || a.project.localeCompare(b.project) || a.port-b.port);
  $('server-count').textContent = state.authenticated ? ports.length : '—'; $('nav-count').textContent = state.authenticated ? ports.length : '—';
  $('workspace-dot').className=`dot${!state.authenticated ? ' unknown' : state.stale ? ' warning' : ''}`; $('workspace-dot').title=state.authenticated ? state.stale ? 'Relevé indisponible' : 'Workspace accessible' : 'Session requise';
  $('port-grid').replaceChildren(...filtered.map(portCard)); $('port-grid').setAttribute('aria-busy',String(state.busy));
  $('empty').hidden=filtered.length>0 || state.busy && !state.data;
  $('login').hidden=state.authenticated || state.stale; $('clear-filter').hidden=!state.authenticated || !(state.query || state.project || state.starredOnly);
  if (!state.authenticated && state.stale) { $('empty-title').textContent='Détection indisponible'; $('empty-description').textContent='L’agent du workspace ne répond pas. Vos liens d’aperçu restent accessibles.'; }
  else if (!state.authenticated) { $('empty-title').textContent='Connecter votre workspace'; $('empty-description').textContent='Votre session Coder donne accès aux serveurs et projets privés.'; }
  else if (ports.length && !filtered.length) { $('empty-title').textContent='Aucun serveur pour ce filtre'; $('empty-description').textContent='Essayez un autre projet, port ou filtre.'; }
  else { $('empty-title').textContent=state.stale ? 'Workspace indisponible' : 'Aucun serveur web en cours'; $('empty-description').textContent=state.stale ? 'Le dernier relevé n’a pas abouti. Réessayez dans quelques instants.' : 'Démarrez un serveur dans un dossier de projet : il apparaîtra automatiquement ici.'; }
  $('filter-all').classList.toggle('selected',!state.starredOnly); $('filter-starred').classList.toggle('selected',state.starredOnly); $('filter-all').setAttribute('aria-pressed',String(!state.starredOnly)); $('filter-starred').setAttribute('aria-pressed',String(state.starredOnly));
  renderProjects();
}
function validInventory(data) { return data && Array.isArray(data.ports) && data.ports.every(p => Number.isInteger(p.port) && p.port>=1024 && p.port<=65535 && typeof p.project==='string' && typeof p.runtime==='string') && Array.isArray(data.projects) && data.projects.every(p=>typeof p.name==='string'&&Array.isArray(p.ports)); }
async function refresh() {
  if (state.busy) return;
  state.busy=true; $('refresh').disabled=true; $('port-grid').setAttribute('aria-busy','true');
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),6500);
  try {
    const response=await fetch('/api/workspace',{credentials:'same-origin',signal:controller.signal,cache:'no-store'});
    if (response.status===401) {
      state.authenticated=false; state.data=null; state.stale=false; $('notice').hidden=true; $('sync-status').textContent='Session Coder requise'; $('last-checked').textContent='Connexion nécessaire pour la détection.'; return;
    }
    if (!response.ok) throw new Error('unavailable');
    const data=await response.json(); if(!validInventory(data))throw new Error('invalid');
    state.data=data; state.authenticated=true; state.stale=false; $('notice').hidden=!data.limited; $('notice').textContent='Le relevé est partiel : une partie des serveurs ou projets dépasse la limite de détection.';
    $('sync-status').textContent='Détection automatique · actualisation toutes les 10 s';
    $('last-checked').textContent=`Dernier relevé à ${new Date(data.checked_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
  } catch {
    state.stale=true; $('notice').hidden=false; $('notice').textContent='Le workspace ne répond pas. Les informations précédentes, si présentes, ne sont plus à jour.'; $('sync-status').textContent='Détection indisponible';
    if (!state.data) { $('empty-title').textContent='Workspace indisponible'; }
  } finally { clearTimeout(timer); state.busy=false; $('refresh').disabled=false; render(); }
}
$('refresh').onclick=refresh; $('search').addEventListener('input',event=>{state.query=event.target.value;render();});
$('filter-all').onclick=()=>{state.starredOnly=false;render();}; $('filter-starred').onclick=()=>{state.starredOnly=true;render();};
$('clear-filter').onclick=()=>{state.query='';state.project='';state.starredOnly=false;$('search').value='';render();};
$('open-port').addEventListener('submit',event=>{event.preventDefault();const number=Number($('port').value);if($('port').reportValidity()&&Number.isInteger(number)&&number>=1024&&number<=65535)location.href=appUrl(number);});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.activeElement===$('search')){$('search').value='';state.query='';render();$('search').blur();}else if((event.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName))||((event.metaKey||event.ctrlKey)&&event.key==='k')){event.preventDefault();$('search').focus();}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
render();refresh();setInterval(()=>{if(!document.hidden)refresh();},10000);
