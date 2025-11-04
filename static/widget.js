(() => {
  const script = document.currentScript;
  const apiBase = script.getAttribute('data-api-base') || 'http://localhost:8000';
  const jwtToken = script.getAttribute('data-token');
  const username = script.getAttribute('data-username');
  const password = script.getAttribute('data-password');
  const initialCategory = script.getAttribute('data-category') || null;

  const state = {
    token: jwtToken || null,
    sessionId: null,
  };

  function el(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'style' && typeof v === 'object') {
        Object.assign(e.style, v);
      } else if (k.startsWith('on') && typeof v === 'function') {
        e.addEventListener(k.substring(2), v);
      } else {
        e.setAttribute(k, v);
      }
    });
    (Array.isArray(children) ? children : [children]).forEach(c => {
      if (typeof c === 'string') e.appendChild(document.createTextNode(c));
      else if (c) e.appendChild(c);
    });
    return e;
  }

  async function loginIfNeeded() {
    if (state.token) return;
    if (!username || !password) {
      throw new Error('Widget requires data-token or data-username and data-password');
    }
    const res = await fetch(`${apiBase}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    if (!res.ok) throw new Error('Login failed');
    const data = await res.json();
    state.token = data.access_token || data.accessToken;
  }

  async function ensureSession() {
    if (state.sessionId) return state.sessionId;
    const res = await fetch(`${apiBase}/chat/sessions`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${state.token}` }
    });
    const data = await res.json();
    state.sessionId = data.session_id;
    return state.sessionId;
  }

  async function queryProducts(q) {
    await loginIfNeeded();
    const sessionId = await ensureSession();
    const res = await fetch(`${apiBase}/api/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.token}`
      },
      body: JSON.stringify({ query: q, session_id: sessionId, category: initialCategory, limit: 8 })
    });
    if (!res.ok) throw new Error('Query failed');
    return res.json();
  }

  async function queryImage(file, qOpt) {
    await loginIfNeeded();
    const sessionId = await ensureSession();
    const fd = new FormData();
    fd.append('session_id', sessionId);
    if (qOpt) fd.append('query', qOpt);
    if (initialCategory) fd.append('category', initialCategory);
    fd.append('image', file);
    const res = await fetch(`${apiBase}/chat/image-query`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${state.token}` },
      body: fd
    });
    if (!res.ok) throw new Error('Image query failed');
    return res.json();
  }

  function renderProducts(container, resp) {
    const products = resp.products || [];
    if (!products.length) {
      container.appendChild(el('div', { style: { color: '#374151', marginBottom: '10px' } }, [resp.response || 'No results']));
      return;
    }
    const grid = el('div', { style: {
      display: 'grid', gridTemplateColumns: '1fr', gap: '10px'
    }});
    products.forEach(p => {
      const card = el('div', { style: {
        display: 'flex', gap: '10px', border: '1px solid #e5e7eb', borderRadius: '8px', padding: '8px'
      }});
      const imgSrc = p.image_url || '';
      const img = el('img', { src: imgSrc || 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', alt: p.name || 'product', style: {
        width: '64px', height: '64px', objectFit: 'cover', borderRadius: '6px', background: '#f3f4f6', border: '1px solid #e5e7eb'
      }});
      const info = el('div', { style: { display: 'flex', flexDirection: 'column', minWidth: 0 } });
      const title = el('div', { style: { fontWeight: '600', color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, [p.name || 'Unnamed product']);
      const desc = el('div', { style: { fontSize: '12px', color: '#4b5563', maxHeight: '3.2em', overflow: 'hidden' } }, [p.description || '']);
      const meta = el('div', { style: { fontSize: '12px', color: '#6b7280', marginTop: '4px' } }, [
        `${p.category || ''}${p.category && p.price ? ' • ' : ''}${p.price || ''}`
      ]);
      info.appendChild(title);
      info.appendChild(desc);
      info.appendChild(meta);
      card.appendChild(img);
      card.appendChild(info);
      grid.appendChild(card);
    });
    container.appendChild(grid);
  }

  // UI
  const container = el('div', { style: {
    position: 'fixed', right: '20px', bottom: '20px', zIndex: '999999'
  }});
  const panel = el('div', { style: {
    width: '320px', height: '420px', borderRadius: '12px', boxShadow: '0 10px 30px rgba(0,0,0,0.15)',
    background: '#fff', overflow: 'hidden', display: 'none', flexDirection: 'column',
    fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Arial',
  }});
  const header = el('div', { style: {
    padding: '12px 14px', background: '#111827', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
  }}, [
    el('div', {}, ['Product Chatbot']),
    el('button', { style: { background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer' }, onclick: () => panel.style.display = 'none' }, ['✕'])
  ]);
  const content = el('div', { style: { padding: '10px', height: '298px', overflowY: 'auto' } });
  const modeRow = el('div', { style: { display: 'flex', gap: '6px', padding: '8px 10px', borderBottom: '1px solid #e5e7eb', alignItems: 'center' } });
  const textModeBtn = el('button', { style: { padding: '6px 10px', borderRadius: '6px', border: '1px solid #e5e7eb', background: '#111827', color: '#fff', cursor: 'pointer' } }, ['Text']);
  const imageModeBtn = el('button', { style: { padding: '6px 10px', borderRadius: '6px', border: '1px solid #e5e7eb', background: '#fff', color: '#111827', cursor: 'pointer' } }, ['Image']);
  modeRow.appendChild(textModeBtn);
  modeRow.appendChild(imageModeBtn);

  const inputRow = el('div', { style: { display: 'flex', gap: '6px', padding: '10px' } });
  const input = el('input', { type: 'text', placeholder: 'Ask about products...', style: {
    flex: '1', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: '8px'
  }});
  const fileInput = el('input', { type: 'file', accept: 'image/*', style: { display: 'none' } });
  const pickBtn = el('button', { style: {
    padding: '10px 12px', background: '#fff', color: '#111827', border: '1px solid #e5e7eb', borderRadius: '8px', cursor: 'pointer'
  }, onclick: () => fileInput.click() }, ['Pick Image']);
  const sendBtn = el('button', { style: {
    padding: '10px 12px', background: '#111827', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer'
  }, onclick: async () => {
    const q = input.value.trim();
    const usingImageMode = imageModeBtn.getAttribute('data-active') === '1';
    try {
      if (usingImageMode) {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          content.appendChild(el('div', { style: { color: '#b91c1c' } }, ['Please select an image first']));
          return;
        }
        const you = el('div', { style: { marginBottom: '10px', color: '#374151' } }, [`You (image${q ? ` + text: ${q}` : ''})`]);
        content.appendChild(you);
        const resp = await queryImage(file, q || null);
        renderProducts(content, resp);
      } else {
        if (!q) return;
        const you = el('div', { style: { marginBottom: '10px', color: '#374151' } }, [`You: ${q}`]);
        content.appendChild(you);
        const resp = await queryProducts(q);
        renderProducts(content, resp);
      }
      input.value = '';
      fileInput.value = '';
      content.scrollTop = content.scrollHeight;
    } catch (e) {
      content.appendChild(el('div', { style: { color: '#b91c1c' } }, ['Error: ' + e.message]));
    }
  } }, ['Send']);
  inputRow.appendChild(input);
  inputRow.appendChild(fileInput);
  inputRow.appendChild(pickBtn);
  inputRow.appendChild(sendBtn);
  panel.appendChild(header);
  panel.appendChild(modeRow);
  panel.appendChild(content);
  panel.appendChild(inputRow);

  const fab = el('button', { style: {
    width: '56px', height: '56px', borderRadius: '50%', background: '#111827', color: '#fff', border: 'none',
    boxShadow: '0 10px 30px rgba(0,0,0,0.2)', cursor: 'pointer', fontSize: '20px'
  }, onclick: () => { panel.style.display = panel.style.display === 'none' ? 'flex' : 'none'; } }, ['💬']);

  // Mode switching logic
  function setMode(isImage) {
    if (isImage) {
      imageModeBtn.style.background = '#111827';
      imageModeBtn.style.color = '#fff';
      imageModeBtn.setAttribute('data-active', '1');
      textModeBtn.style.background = '#fff';
      textModeBtn.style.color = '#111827';
      textModeBtn.removeAttribute('data-active');
      pickBtn.style.display = '';
      fileInput.style.display = 'none'; // kept hidden; triggered via pickBtn
      input.placeholder = 'Optional: add text with your image...';
    } else {
      textModeBtn.style.background = '#111827';
      textModeBtn.style.color = '#fff';
      textModeBtn.setAttribute('data-active', '1');
      imageModeBtn.style.background = '#fff';
      imageModeBtn.style.color = '#111827';
      imageModeBtn.removeAttribute('data-active');
      pickBtn.style.display = 'none';
      input.placeholder = 'Ask about products...';
    }
  }
  textModeBtn.addEventListener('click', () => setMode(false));
  imageModeBtn.addEventListener('click', () => setMode(true));
  setMode(false);

  container.appendChild(panel);
  container.appendChild(fab);
  document.body.appendChild(container);
})();


