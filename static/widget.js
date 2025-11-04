(() => {
  const script = document.currentScript;
  const apiBase = script.getAttribute('data-api-base') || 'http://localhost:8000';
  const jwtToken = script.getAttribute('data-token');
  const username = script.getAttribute('data-username');
  const password = script.getAttribute('data-password');
  const initialCategory = script.getAttribute('data-category') || null;

  const state = { token: jwtToken || null, sessionId: null };

  // Utility: create elements
  function el(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.substring(2), v);
      else e.setAttribute(k, v);
    });
    (Array.isArray(children) ? children : [children]).forEach(c => {
      if (typeof c === 'string') e.appendChild(document.createTextNode(c));
      else if (c) e.appendChild(c);
    });
    return e;
  }

  // --- API LOGIN / SESSION ---
  async function loginIfNeeded() {
    if (state.token) return;
    if (!username || !password)
      throw new Error('Widget requires data-token or data-username and data-password');
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
      headers: { Authorization: `Bearer ${state.token}` }
    });
    const data = await res.json();
    state.sessionId = data.session_id;
    return state.sessionId;
  }

  // --- QUERY HANDLERS ---
  async function queryProducts(q) {
    await loginIfNeeded();
    const sessionId = await ensureSession();
    const res = await fetch(`${apiBase}/api/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${state.token}`
      },
      body: JSON.stringify({
        query: q,
        session_id: sessionId,
        category: initialCategory,
        limit: 8
      })
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
      headers: { Authorization: `Bearer ${state.token}` },
      body: fd
    });
    if (!res.ok) throw new Error('Image query failed');
    return res.json();
  }

  // --- UI RENDERING ---
  function renderProducts(container, resp) {
    const products = resp.products || [];
    if (!products.length) {
      container.appendChild(
        el('div', { style: { color: '#4B0082', marginBottom: '10px' } }, [
          resp.response || 'No results found.'
        ])
      );
      return;
    }

    const grid = el('div', {
      style: { display: 'grid', gridTemplateColumns: '1fr', gap: '10px' }
    });

    products.forEach(p => {
      const card = el('div', {
        style: {
          display: 'flex',
          gap: '10px',
          border: '1px solid #d8b4fe',
          borderRadius: '10px',
          padding: '10px',
          background: '#f5f3ff'
        }
      });

      const img = el('img', {
        src:
          p.image_url ||
          'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==',
        alt: p.name || 'product',
        style: {
          width: '80px',
          height: '80px',
          objectFit: 'cover',
          borderRadius: '8px',
          background: '#f3e8ff',
          border: '1px solid #d8b4fe'
        }
      });

      const info = el('div', {
        style: { display: 'flex', flexDirection: 'column', minWidth: 0 }
      });

      const title = el(
        'div',
        {
          style: {
            fontWeight: '600',
            color: '#4B0082',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }
        },
        [p.name || 'Unnamed product']
      );

      const desc = el(
        'div',
        {
          style: {
            fontSize: '13px',
            color: '#6b21a8',
            maxHeight: '3.2em',
            overflow: 'hidden'
          }
        },
        [p.description || '']
      );

      const meta = el(
        'div',
        {
          style: {
            fontSize: '12px',
            color: '#7e22ce',
            marginTop: '4px'
          }
        },
        [`${p.category || ''}${p.category && p.price ? ' • ' : ''}${p.price || ''}`]
      );

      info.appendChild(title);
      info.appendChild(desc);
      info.appendChild(meta);
      card.appendChild(img);
      card.appendChild(info);
      grid.appendChild(card);
    });

    container.appendChild(grid);
  }

  // --- MAIN WIDGET ---
  const container = el('div', {
    style: { position: 'fixed', right: '25px', bottom: '25px', zIndex: '999999' }
  });

  const panel = el('div', {
    style: {
      width: '480px',
      height: '600px',
      borderRadius: '18px',
      boxShadow: '0 12px 35px rgba(128, 0, 128, 0.3)',
      background: '#fff',
      overflow: 'hidden',
      display: 'none',
      flexDirection: 'column',
      fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Arial'
    }
  });

  const header = el(
    'div',
    {
      style: {
        padding: '14px 16px',
        background: '#7e22ce',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontWeight: '600'
      }
    },
    [
      el('div', {}, ['E-commerce Chatbot']),
      el(
        'button',
        {
          style: {
            background: 'transparent',
            border: 'none',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '16px'
          },
          onclick: () => (panel.style.display = 'none')
        },
        ['✕']
      )
    ]
  );

  const content = el('div', {
    style: {
      padding: '12px',
      height: '400px',
      overflowY: 'auto',
      background: '#faf5ff'
    }
  });

  // --- MODE ROW ---
  const modeRow = el('div', {
    style: {
      display: 'flex',
      gap: '6px',
      padding: '8px 10px',
      borderBottom: '1px solid #e9d5ff',
      alignItems: 'center',
      background: '#f3e8ff'
    }
  });

  const textModeBtn = el(
    'button',
    {
      style: {
        padding: '6px 10px',
        borderRadius: '8px',
        border: '1px solid #c084fc',
        background: '#7e22ce',
        color: '#fff',
        cursor: 'pointer'
      }
    },
    ['Text']
  );

  const imageModeBtn = el(
    'button',
    {
      style: {
        padding: '6px 10px',
        borderRadius: '8px',
        border: '1px solid #c084fc',
        background: '#fff',
        color: '#7e22ce',
        cursor: 'pointer'
      }
    },
    ['Image']
  );

  modeRow.appendChild(textModeBtn);
  modeRow.appendChild(imageModeBtn);

  // --- INPUT SECTION ---
  const inputRow = el('div', {
    style: {
      display: 'flex',
      gap: '6px',
      padding: '10px',
      background: '#faf5ff',
      alignItems: 'center'
    }
  });

  const input = el('input', {
    type: 'text',
    placeholder: 'Ask about products...',
    style: {
      flex: '1',
      padding: '10px 12px',
      border: '1px solid #c084fc',
      borderRadius: '8px'
    }
  });

  const fileInput = el('input', {
    type: 'file',
    accept: 'image/*',
    style: { display: 'none' }
  });

  const pickBtn = el(
    'button',
    {
      style: {
        padding: '10px 12px',
        background: '#fff',
        color: '#7e22ce',
        border: '1px solid #c084fc',
        borderRadius: '8px',
        cursor: 'pointer'
      },
      onclick: () => fileInput.click()
    },
    ['📷']
  );

  const sendBtn = el(
    'button',
    {
      style: {
        padding: '10px 12px',
        background: '#7e22ce',
        color: '#fff',
        border: 'none',
        borderRadius: '8px',
        cursor: 'pointer'
      }
    },
    ['Send']
  );

  // --- Image Preview Box ---
  const previewBox = el('div', {
    style: {
      display: 'none',
      flexDirection: 'column',
      alignItems: 'center',
      background: '#f3e8ff',
      padding: '10px',
      borderRadius: '10px',
      margin: '0 10px 10px',
      border: '1px solid #d8b4fe'
    }
  });

  const previewImg = el('img', {
    style: {
      maxWidth: '100px',
      maxHeight: '100px',
      borderRadius: '8px',
      marginBottom: '5px',
      objectFit: 'cover'
    }
  });

  const removePreviewBtn = el(
    'button',
    {
      style: {
        background: '#7e22ce',
        color: '#fff',
        border: 'none',
        borderRadius: '6px',
        padding: '4px 8px',
        cursor: 'pointer',
        fontSize: '12px'
      },
      onclick: () => {
        previewBox.style.display = 'none';
        fileInput.value = '';
      }
    },
    ['Remove Image']
  );

  previewBox.appendChild(previewImg);
  previewBox.appendChild(removePreviewBtn);

  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = e => {
        previewImg.src = e.target.result;
        previewBox.style.display = 'flex';
      };
      reader.readAsDataURL(file);
    }
  });

  // --- SEND LOGIC ---
  sendBtn.onclick = async () => {
    const q = input.value.trim();
    const usingImageMode = imageModeBtn.getAttribute('data-active') === '1';
    try {
      if (usingImageMode) {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          content.appendChild(
            el('div', { style: { color: '#b91c1c' } }, ['Please select an image first'])
          );
          return;
        }

        // Show user image message
        const youBlock = el('div', { style: { marginBottom: '10px' } }, [
          el('div', { style: { color: '#6b21a8', fontWeight: '600' } }, [
            `You (image${q ? ` + text: ${q}` : ''})`
          ]),
          el('img', {
            src: previewImg.src,
            style: {
              maxWidth: '120px',
              maxHeight: '120px',
              borderRadius: '8px',
              marginTop: '5px',
              border: '1px solid #d8b4fe'
            }
          })
        ]);
        content.appendChild(youBlock);

        const resp = await queryImage(file, q || null);
        renderProducts(content, resp);
        previewBox.style.display = 'none';
      } else {
        if (!q) return;
        const you = el('div', { style: { marginBottom: '10px', color: '#6b21a8' } }, [`You: ${q}`]);
        content.appendChild(you);
        const resp = await queryProducts(q);
        renderProducts(content, resp);
      }
      input.value = '';
      fileInput.value = '';
      content.scrollTop = content.scrollHeight;
    } catch (e) {
      content.appendChild(
        el('div', { style: { color: '#b91c1c' } }, ['Error: ' + e.message])
      );
    }
  };

  inputRow.appendChild(input);
  inputRow.appendChild(fileInput);
  inputRow.appendChild(pickBtn);
  inputRow.appendChild(sendBtn);

  panel.appendChild(header);
  panel.appendChild(modeRow);
  panel.appendChild(content);
  panel.appendChild(previewBox);
  panel.appendChild(inputRow);

  // --- Floating Button ---
  const fab = el(
    'button',
    {
      style: {
        width: '75px',
        height: '75px',
        borderRadius: '50%',
        background: '#7e22ce',
        color: '#fff',
        border: 'none',
        boxShadow: '0 10px 30px rgba(128,0,128,0.3)',
        cursor: 'pointer',
        fontSize: '26px'
      },
      onclick: () => {
        panel.style.display = panel.style.display === 'none' ? 'flex' : 'none';
      }
    },
    ['💬']
  );

  // --- Mode Switch ---
  function setMode(isImage) {
    if (isImage) {
      imageModeBtn.style.background = '#7e22ce';
      imageModeBtn.style.color = '#fff';
      imageModeBtn.setAttribute('data-active', '1');
      textModeBtn.style.background = '#fff';
      textModeBtn.style.color = '#7e22ce';
      textModeBtn.removeAttribute('data-active');
      pickBtn.style.display = '';
      input.placeholder = 'Optional: add text with your image...';
    } else {
      textModeBtn.style.background = '#7e22ce';
      textModeBtn.style.color = '#fff';
      textModeBtn.setAttribute('data-active', '1');
      imageModeBtn.style.background = '#fff';
      imageModeBtn.style.color = '#7e22ce';
      imageModeBtn.removeAttribute('data-active');
      pickBtn.style.display = 'none';
      previewBox.style.display = 'none';
      fileInput.value = '';
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
