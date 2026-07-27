const $ = (selector) => document.querySelector(selector);
const goodsKey = new URLSearchParams(location.search).get('product') || '';
const state = { product: null, comments: [], uploadImages: [], avatar: null, adminKey: sessionStorage.getItem('ldxp-admin-key') || '', adminVerified: false, metrics: {} };
const productEl = $('#commentProduct');
const listEl = $('#commentList');
const toastEl = $('#commentToast');
const adminTokenEl = $('#commentAdminToken');
const metricEl = $('#commentMetric');

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
const api = async (path, options = {}) => {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) { const error = new Error(payload.error || `Request failed (${response.status})`); error.status = response.status; throw error; }
  return payload;
};
function toast(message, error = false) {
  toastEl.textContent = message; toastEl.classList.toggle('error', error); toastEl.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => toastEl.classList.remove('show'), 3000);
}
function relativeTime(timestamp) {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - Number(timestamp || 0)));
  if (seconds < 60) return '刚刚'; if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`; return `${Math.floor(seconds / 86400)} 天前`;
}
function renderProduct() {
  const product = state.product;
  if (!product) return;
  const image = product.image ? `<img src="${escapeHtml(product.image)}" alt="" referrerpolicy="no-referrer">` : '<span>LDXP</span>';
  productEl.innerHTML = `<div class="comment-product-image">${image}</div><div><small>${escapeHtml(product.source_name || product.source_token)}</small><h2>${escapeHtml(product.name)}</h2><strong>¥${Number(product.price || 0).toLocaleString('zh-CN')}</strong></div>`;
}
function renderComments() {
  $('#commentCount').textContent = `${state.comments.length} 条评论`;
  if (!state.comments.length) { listEl.innerHTML = '<div class="comment-empty">暂无评论，等待第一条分享。</div>'; return; }
  listEl.innerHTML = state.comments.map((comment) => {
    const images = (comment.images || []).map((url) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(url)}" alt="评论图片" loading="lazy"></a>`).join('');
    const pin = comment.pinned ? '<span class="comment-pin">置顶</span>' : '';
    const adminBadge = comment.is_admin ? '<span class="comment-admin-badge">管理员认证</span>' : comment.admin_verified ? '<span class="comment-verified-badge">管理员已认证</span>' : '';
    const controls = state.adminVerified ? `<button class="comment-pin-toggle" data-id="${escapeHtml(comment.id)}" data-pinned="${comment.pinned}">${comment.pinned ? '取消置顶' : '置顶'}</button><button class="comment-pin-toggle" data-verify="${escapeHtml(comment.id)}" data-verified="${comment.admin_verified}">${comment.admin_verified ? '取消认证' : '认证评论'}</button>` : '';
    const initial = escapeHtml(String(comment.author || '匿名用户').trim().slice(0, 1) || '匿');
    const avatar = comment.avatar ? `<img class="comment-avatar" src="${escapeHtml(comment.avatar)}" alt="${escapeHtml(comment.author || '匿名用户')} 的头像">` : `<span class="comment-avatar default-avatar">${initial}</span>`;
    const ratings = [['商品', comment.product_score], ['商铺', comment.shop_score], ['体验', comment.experience_score]].filter(([, score]) => score !== null && score !== undefined).map(([name, score]) => `<span class="tag">${name} ${Number(score).toFixed(1)} ★</span>`).join('');
    const replies = (comment.replies || []).map((reply) => `<div class="comment-reply"><strong>${escapeHtml(reply.author || '匿名用户')}${reply.is_admin ? ' · 管理员认证' : ''}</strong><span>${escapeHtml(reply.body)}</span></div>`).join('');
    return `<article class="comment-item ${comment.pinned ? 'pinned' : ''}"><div class="comment-author">${avatar}<strong>${escapeHtml(comment.author || '匿名用户')}</strong>${adminBadge}${pin}<time>${relativeTime(comment.created_at)}</time>${controls}</div>${comment.body ? `<p>${escapeHtml(comment.body)}</p>` : ''}${ratings ? `<div class="tags">${ratings}</div>` : ''}${images ? `<div class="comment-images">${images}</div>` : ''}<div class="comment-replies">${replies}</div><form class="reply-form" data-comment-id="${escapeHtml(comment.id)}"><textarea maxlength="200" placeholder="回复这条评论…"></textarea><div><button type="button" data-emoji="😀">😀</button><button type="button" data-emoji="👍">👍</button><button type="button" data-emoji="❤️">❤️</button><button type="submit">回复</button></div></form></article>`;
  }).join('');
  metricEl.textContent = state.metrics.rating_count ? `评论 ${state.metrics.comment_count || state.comments.length} 条 · 加权评分 ${Number(state.metrics.weighted_score).toFixed(2)} · ${state.metrics.rating_count} 项评分` : `评论 ${state.metrics.comment_count || state.comments.length} 条 · 暂无参与评分`;
}
async function load() {
  if (!goodsKey) { productEl.innerHTML = '<p>缺少商品标识。</p>'; return; }
  try {
    const [productResult, commentResult] = await Promise.all([
      api(`api/products/visible?key=${encodeURIComponent(goodsKey)}`), api(`api/products/${encodeURIComponent(goodsKey)}/comments`),
    ]);
    state.product = productResult.products?.[0] || null;
    if (!state.product) throw new Error('商品不存在或已下架。');
    state.comments = commentResult.comments || []; state.metrics = commentResult.metrics || {}; renderProduct(); renderComments();
  } catch (error) { productEl.innerHTML = `<p>${escapeHtml(error.message)}</p>`; }
}
function canvasJpeg(file, maxSide = 1600, quality = .78) {
  return new Promise((resolve, reject) => {
    const image = new Image(); const source = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(source); const scale = Math.min(1, maxSide / Math.max(image.width, image.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale));
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => { if (!blob) reject(new Error('图片转换失败。')); else { const reader = new FileReader(); reader.onload = () => resolve({ data: reader.result, preview: URL.createObjectURL(blob) }); reader.onerror = () => reject(new Error('图片读取失败。')); reader.readAsDataURL(blob); } }, 'image/jpeg', quality);
    }; image.onerror = () => { URL.revokeObjectURL(source); reject(new Error('无法读取该图片。')); }; image.src = source;
  });
}
function renderAvatarPreview() {
  const preview = $('#commentAvatarPreview');
  if (state.avatar?.preview) {
    preview.outerHTML = `<img id="commentAvatarPreview" class="comment-avatar" src="${escapeHtml(state.avatar.preview)}" alt="待上传头像">`;
  } else {
    preview.outerHTML = '<span id="commentAvatarPreview" class="comment-avatar default-avatar">匿</span>';
  }
}
$('#commentAvatar').addEventListener('change', async (event) => {
  const file = event.target.files?.[0]; event.target.value = '';
  if (!file) return;
  if (!/^image\/(png|jpeg)$/.test(file.type)) { toast('头像只支持 PNG 或 JPEG 图片。', true); return; }
  try {
    const avatar = await canvasJpeg(file, 96, .76);
    if (String(avatar.data).length > 140_000) { URL.revokeObjectURL(avatar.preview); throw new Error('头像压缩后仍过大，请换一张图片。'); }
    if (state.avatar?.preview) URL.revokeObjectURL(state.avatar.preview);
    state.avatar = avatar; renderAvatarPreview();
  } catch (error) { toast(error.message, true); }
});
function renderUploadPreviews() { $('#commentImagePreview').innerHTML = state.uploadImages.map((item, index) => `<span><img src="${item.preview}" alt="待上传图片"><button type="button" data-remove-image="${index}">×</button></span>`).join(''); }
$('#commentImages').addEventListener('change', async (event) => {
  const files = [...event.target.files]; event.target.value = '';
  for (const file of files) {
    if (state.uploadImages.length >= 5) { toast('最多选择 5 张图片。', true); break; }
    if (!/^image\/(png|jpeg)$/.test(file.type)) { toast('只支持 PNG 或 JPEG 图片。', true); continue; }
    try { const item = await canvasJpeg(file); if (String(item.data).length > 1_200_000) { URL.revokeObjectURL(item.preview); toast('图片压缩后仍过大，请换一张。', true); } else state.uploadImages.push(item); }
    catch (error) { toast(error.message, true); }
  }
  renderUploadPreviews();
});
$('#commentImagePreview').addEventListener('click', (event) => { const button = event.target.closest('[data-remove-image]'); if (!button) return; const [item] = state.uploadImages.splice(Number(button.dataset.removeImage), 1); if (item) URL.revokeObjectURL(item.preview); renderUploadPreviews(); });
$('#commentForm').addEventListener('submit', async (event) => {
  event.preventDefault(); const body = $('#commentBody').value.trim();
  const scores = {}; document.querySelectorAll('.score-fields > div').forEach((field) => { if (field.querySelector('input').checked) scores[field.dataset.scoreField] = Number(field.dataset.score || 0); });
  if (!body && !state.uploadImages.length && !Object.keys(scores).length) { toast('请填写评论、添加图片或参与评分。', true); return; }
  const button = event.currentTarget.querySelector('button[type="submit"]'); button.disabled = true;
  try {
    const result = await api(`api/products/${encodeURIComponent(goodsKey)}/comments`, { method: 'POST', headers: state.adminVerified ? { 'X-LDXP-Admin-Key': state.adminKey } : {}, body: JSON.stringify({ author: $('#commentAuthor').value.trim(), avatar: state.avatar?.data || '', body, images: state.uploadImages.map((item) => item.data), scores }) });
    state.comments.unshift(result.comment); state.metrics = result.metrics || state.metrics; $('#commentBody').value = ''; state.uploadImages.forEach((item) => URL.revokeObjectURL(item.preview)); state.uploadImages = []; if (state.avatar?.preview) URL.revokeObjectURL(state.avatar.preview); state.avatar = null; renderAvatarPreview(); renderUploadPreviews(); renderComments(); toast('评论已发布。');
  } catch (error) { toast(error.message, true); } finally { button.disabled = false; }
});
listEl.addEventListener('click', async (event) => { const emoji = event.target.closest('[data-emoji]'); if (emoji) { const target = emoji.closest('form')?.querySelector('textarea'); if (target) { target.value += emoji.dataset.emoji; target.focus(); } return; } const button = event.target.closest('.comment-pin-toggle'); if (!button) return; try { if (button.dataset.verify) { await api(`api/products/${encodeURIComponent(goodsKey)}/comments/${button.dataset.verify}/verify`, { method: 'POST', headers: { 'X-LDXP-Admin-Key': state.adminKey }, body: JSON.stringify({ verified: button.dataset.verified !== 'true' }) }); await load(); return; } const result = await api(`api/products/${encodeURIComponent(goodsKey)}/comments/${button.dataset.id}/pin`, { method: 'POST', headers: { 'X-LDXP-Admin-Key': state.adminKey }, body: JSON.stringify({ pinned: button.dataset.pinned !== 'true' }) }); const index = state.comments.findIndex((comment) => comment.id === result.comment.id); if (index >= 0) state.comments[index] = result.comment; state.comments.sort((a, b) => Number(b.pinned) - Number(a.pinned) || Number(b.pinned_at) - Number(a.pinned_at) || Number(b.created_at) - Number(a.created_at)); renderComments(); } catch (error) { toast(error.message, true); } });
listEl.addEventListener('submit', async (event) => { const form = event.target.closest('.reply-form'); if (!form) return; event.preventDefault(); const body = form.querySelector('textarea').value.trim(); if (!body) return; try { const result = await api(`api/products/${encodeURIComponent(goodsKey)}/comments/${form.dataset.commentId}/replies`, { method: 'POST', headers: state.adminVerified ? { 'X-LDXP-Admin-Key': state.adminKey } : {}, body: JSON.stringify({ author: $('#commentAuthor').value.trim(), body }) }); const comment = state.comments.find((item) => item.id === form.dataset.commentId); if (comment) { comment.replies = [...(comment.replies || []), result.reply]; renderComments(); } } catch (error) { toast(error.message, true); } });
adminTokenEl.value = state.adminKey;
adminTokenEl.addEventListener('input', () => { state.adminKey = adminTokenEl.value.trim(); state.adminVerified = false; if (state.adminKey) sessionStorage.setItem('ldxp-admin-key', state.adminKey); else sessionStorage.removeItem('ldxp-admin-key'); renderComments(); });
$('#commentAdminVerify').addEventListener('click', async () => { if (!state.adminKey) { toast('请输入管理员 Token', true); return; } try { await api('api/admin/verify', { method: 'POST', headers: { 'X-LDXP-Admin-Key': state.adminKey } }); state.adminVerified = true; renderComments(); toast('管理员认证成功'); } catch (error) { state.adminVerified = false; toast(error.message, true); } });
$('#commentRefresh').addEventListener('click', () => { void load(); });
document.querySelectorAll('.score-fields > div').forEach((field) => { field.querySelector('.stars').innerHTML = [1,2,3,4,5].map((score) => `<button type="button" data-score="${score}">★</button>`).join(''); });
document.querySelector('.score-fields').addEventListener('click', (event) => { const button = event.target.closest('[data-score]'); if (!button) return; const field = button.closest('[data-score-field]'); field.dataset.score = button.dataset.score; field.querySelectorAll('[data-score]').forEach((star) => star.classList.toggle('active', Number(star.dataset.score) <= Number(button.dataset.score))); });
$('#commentForm').addEventListener('click', (event) => { const emoji = event.target.closest('[data-emoji]'); if (!emoji) return; $('#commentBody').value += emoji.dataset.emoji; $('#commentBody').focus(); });
load();
