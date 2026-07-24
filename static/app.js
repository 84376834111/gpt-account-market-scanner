const state = {
  products: new Map(),
  sources: [],
  categories: [],
  stats: {},
  selectedCategory: 'all',
  search: '',
  stockOnly: true,
  sort: 'price',
  scanning: false,
  localScanning: false,
  localScanTarget: '',
  autoScanEnabled: false,
  scanIntervalMinutes: 15,
  sourceInterval: 15,
  pendingProducts: new Map(),
  pendingRemovals: new Set(),
  refreshingTags: new Set(),
  refreshTimers: new Map(),
  refreshingProducts: new Set(),
  renderQueued: false,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  grid: $('#productGrid'), empty: $('#emptyState'), tabs: $('#categoryTabs'),
  total: $('#totalStat'), stock: $('#stockStat'), low: $('#lowStat'), source: $('#sourceStat'),
  sourceSub: $('#sourceStatSub'), result: $('#resultCount'), lastUpdate: $('#lastUpdate'),
  scanPulse: $('#scanPulse'), scanText: $('#scanStateText'),
  localScanButton: $('#localScanButton'), localScanLabel: $('#localScanButton .local-scan-label'),
  filteredLocalScanButton: $('#filteredLocalScanButton'), filteredScanLabel: $('#filteredLocalScanButton .filtered-scan-label'),
  scanDetail: $('#scanDetail'), stream: $('#streamStatus'), dialog: $('#sourceDialog'),
  sourceList: $('#sourceList'), sourceInput: $('#sourceInput'), toast: $('#toast'),
  historyDialog: $('#historyDialog'), historyTitle: $('#historyTitle'), historyShop: $('#historyShop'),
  historyToken: $('#historyToken'), historySummary: $('#historySummary'), historyChart: $('#historyChart'),
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
}[char]));

const money = (value) => Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const dateTime = (timestamp) => timestamp ? new Date(timestamp * 1000).toLocaleString('zh-CN', { hour12: false }) : '尚未扫描';
const relativeTime = (timestamp) => {
  if (!timestamp) return '未知';
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
};

function toast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { elements.toast.className = 'toast'; }, 2800);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { ...options, headers });
  let payload = {};
  try { payload = await response.json(); } catch { /* nginx errors may not be json */ }
  if (!response.ok) {
    const error = new Error(payload.error || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

async function loadState() {
  try {
    const payload = await api('api/state');
    state.products = new Map((payload.products || []).map((product) => [product.goods_key, product]));
    state.sources = payload.sources || [];
    state.categories = payload.categories || [];
    state.stats = payload.stats || {};
    state.scanning = Boolean(payload.scanning);
    state.autoScanEnabled = Boolean(payload.auto_scan_enabled);
    state.scanIntervalMinutes = Math.max(1, Math.round(Number(payload.scan_interval || 900) / 60));
    state.sourceInterval = Number(payload.source_interval || 15);
    updateStats();
    renderTabs();
    renderProducts();
    renderSources();
    setScanning(state.scanning, state.scanning ? '正在采集公开店铺' : '自动扫描已关闭');
  } catch (error) {
    toast(error.message, true);
    elements.empty.hidden = false;
  }
}

function categoryCounts() {
  const counts = Object.fromEntries(state.categories.map((category) => [category.key, 0]));
  for (const product of state.products.values()) {
    if (!product.active) continue;
    for (const tag of product.tags || []) counts[tag] = (counts[tag] || 0) + 1;
  }
  return counts;
}

function renderTabs() {
  const counts = categoryCounts();
  const tabs = [{ key: 'all', label: '全部', count: state.products.size }, ...state.categories.map((item) => ({ ...item, count: counts[item.key] || 0 }))];
  elements.tabs.innerHTML = tabs.map((tab) => `
    <button type="button" class="category ${state.selectedCategory === tab.key ? 'active' : ''} ${state.refreshingTags.has(tab.key) ? 'refreshing' : ''}" data-category="${escapeHtml(tab.key)}" role="tab" aria-selected="${state.selectedCategory === tab.key}" aria-busy="${state.refreshingTags.has(tab.key)}">
      ${escapeHtml(tab.label)} <b>${tab.count}</b><i class="refresh-indicator" title="正在刷新" aria-hidden="true"></i>
    </button>`).join('');
}

function stopTagRefreshing(key) {
  const timer = state.refreshTimers.get(key);
  if (timer) clearTimeout(timer);
  state.refreshTimers.delete(key);
  state.refreshingTags.delete(key);
  const tab = [...elements.tabs.querySelectorAll('[data-category]')].find((item) => item.dataset.category === key);
  if (tab) {
    tab.classList.remove('refreshing');
    tab.setAttribute('aria-busy', 'false');
  }
}

function markTagsRefreshing(tags = []) {
  for (const key of new Set(['all', ...tags])) {
    const previous = state.refreshTimers.get(key);
    if (previous) clearTimeout(previous);
    state.refreshingTags.add(key);
    const tab = [...elements.tabs.querySelectorAll('[data-category]')].find((item) => item.dataset.category === key);
    if (tab) {
      tab.classList.add('refreshing');
      tab.setAttribute('aria-busy', 'true');
    }
    state.refreshTimers.set(key, setTimeout(() => stopTagRefreshing(key), 900));
  }
}

function clearRefreshingTags() {
  for (const key of [...state.refreshingTags]) stopTagRefreshing(key);
}

function updateTabCounts() {
  const counts = categoryCounts();
  for (const tab of elements.tabs.querySelectorAll('[data-category]')) {
    const key = tab.dataset.category;
    const count = key === 'all' ? [...state.products.values()].filter((product) => product.active).length : (counts[key] || 0);
    const badge = tab.querySelector('b');
    if (badge && badge.textContent !== String(count)) badge.textContent = String(count);
  }
}

function productMatchesFilters(product) {
  if (!product?.active) return false;
  if (state.selectedCategory !== 'all' && !(product.tags || []).includes(state.selectedCategory)) return false;
  if (state.stockOnly && !product.in_stock) return false;
  const query = state.search.trim().toLocaleLowerCase();
  return !query || `${product.name} ${product.source_name} ${product.category_name}`.toLocaleLowerCase().includes(query);
}

function compareProducts(a, b) {
  if (state.sort === 'price') {
    return Number(a.price) - Number(b.price)
      || String(a.name).localeCompare(String(b.name), 'zh-CN')
      || String(a.goods_key).localeCompare(String(b.goods_key));
  }
  if (state.sort === 'stock') return Number(b.stock_count) - Number(a.stock_count) || Number(a.price) - Number(b.price);
  return Number(b.changed_at) - Number(a.changed_at) || Number(a.price) - Number(b.price);
}

function filteredProducts() {
  return [...state.products.values()].filter(productMatchesFilters).sort(compareProducts);
}

function productTags(product) {
  const labels = new Map(state.categories.map((category) => [category.key, category.label]));
  const tagHtml = (product.tags || []).map((tag) => `<span class="tag">${escapeHtml(labels.get(tag) || tag)}</span>`).join('');
  const stockClass = product.in_stock ? 'stock' : 'out';
  const stockLabel = product.stock_count < 0 ? '库存未知' : product.in_stock ? `库存 ${product.stock_count}` : '已缺货';
  return `${tagHtml}<span class="tag ${stockClass}">${stockLabel}</span>`;
}

function marketPrice(product) {
  return Number(product.market_price) > Number(product.price)
    ? `<div class="market-price">参考 ¥${money(product.market_price)}</div>` : '';
}

function productCard(product, index) {
  const image = product.image
    ? `<img class="product-image" src="${escapeHtml(product.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=\'product-image fallback\'>L</span>'">`
    : '<span class="product-image fallback">L</span>';
  const refreshing = state.refreshingProducts.has(product.goods_key);
  return `<article class="product-card${refreshing ? ' product-refreshing' : ''}" data-key="${escapeHtml(product.goods_key)}">
    <a class="product-card-link" href="${escapeHtml(product.link)}" target="_blank" rel="noopener noreferrer" aria-label="查看 ${escapeHtml(product.name)}"></a>
    <button class="product-history" type="button" title="查看价格走势" aria-label="查看 ${escapeHtml(product.name)} 的价格走势"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 17 5-6 4 3 7-9"/></svg></button>
    <button class="product-refresh" type="button" title="只刷新这个商品" aria-label="只刷新 ${escapeHtml(product.name)}" aria-busy="${refreshing}" ${refreshing ? 'disabled' : ''}><span aria-hidden="true">↻</span></button>
    <div class="product-head">${image}<div class="product-title">
      <span class="product-title-link">${escapeHtml(product.name)}</span>
      <div class="shop-line">${escapeHtml(product.source_name || product.source_token)} · ${escapeHtml(product.category_name || product.goods_type)}</div>
    </div></div>
    <div class="tags">${productTags(product)}</div>
    <div class="price-row"><div class="price-block"><div class="price">${money(product.price)}</div><div class="market-slot">${marketPrice(product)}</div></div>
      <div class="product-meta"><span class="stock-number">${escapeHtml(product.source_token)}</span><span class="updated">${relativeTime(product.last_seen)}</span></div>
    </div>
  </article>`;
}

function createProductCard(product) {
  const template = document.createElement('template');
  template.innerHTML = productCard(product, 0).trim();
  return template.content.firstElementChild;
}

function findProductCard(goodsKey) {
  return [...elements.grid.children].find((card) => card.dataset.key === goodsKey) || null;
}

function updateProductCard(card, product) {
  const link = card.querySelector('.product-card-link');
  link.href = product.link;
  link.setAttribute('aria-label', `查看 ${product.name}`);
  const title = card.querySelector('.product-title-link');
  if (title.textContent !== product.name) title.textContent = product.name;
  const refreshButton = card.querySelector('.product-refresh');
  refreshButton.setAttribute('aria-label', `只刷新 ${product.name}`);
  card.querySelector('.product-history').setAttribute('aria-label', `查看 ${product.name} 的价格走势`);
  const shop = card.querySelector('.shop-line');
  const shopText = `${product.source_name || product.source_token} · ${product.category_name || product.goods_type}`;
  if (shop.textContent !== shopText) shop.textContent = shopText;
  card.querySelector('.tags').innerHTML = productTags(product);
  const price = card.querySelector('.price');
  const priceText = money(product.price);
  if (price.textContent !== priceText) price.textContent = priceText;
  card.querySelector('.market-slot').innerHTML = marketPrice(product);
  card.querySelector('.stock-number').textContent = product.source_token;
  card.querySelector('.updated').textContent = relativeTime(product.last_seen);
}

function setProductRefreshing(goodsKey, refreshing) {
  if (refreshing) state.refreshingProducts.add(goodsKey);
  else state.refreshingProducts.delete(goodsKey);
  const card = findProductCard(goodsKey);
  if (!card) return;
  card.classList.toggle('product-refreshing', refreshing);
  const button = card.querySelector('.product-refresh');
  button.disabled = refreshing;
  button.setAttribute('aria-busy', String(refreshing));
}

function applySingleProductRefresh(product) {
  state.products.set(product.goods_key, product);
  let card = findProductCard(product.goods_key);
  if (!productMatchesFilters(product)) {
    card?.remove();
  } else if (card) {
    updateProductCard(card, product);
  } else {
    card = createProductCard(product);
    elements.grid.appendChild(card);
  }
  updateStats();
  updateTabCounts();
  updateVisibleSummary();
}

function applySingleProductRemoval(goodsKey) {
  state.products.delete(goodsKey);
  findProductCard(goodsKey)?.remove();
  updateStats();
  updateTabCounts();
  updateVisibleSummary();
}

function positionProductCard(card, product) {
  const before = [...elements.grid.children]
    .filter((candidate) => candidate !== card)
    .find((candidate) => {
      const other = state.products.get(candidate.dataset.key);
      return other && compareProducts(product, other) < 0;
    });
  if (before) {
    if (card.nextElementSibling !== before) elements.grid.insertBefore(card, before);
  } else if (card !== elements.grid.lastElementChild) {
    elements.grid.appendChild(card);
  }
}

function reconcileProductCard(product, change) {
  let card = findProductCard(product.goods_key);
  if (!productMatchesFilters(product)) {
    if (card) card.remove();
    return;
  }
  if (!card) {
    card = createProductCard(product);
    elements.grid.appendChild(card);
    positionProductCard(card, product);
    return;
  }
  if (change === 'unchanged') {
    card.querySelector('.updated').textContent = relativeTime(product.last_seen);
    return;
  }
  updateProductCard(card, product);
  positionProductCard(card, product);
}

function updateVisibleSummary() {
  const count = elements.grid.childElementCount;
  elements.result.textContent = `${count} 件`;
  elements.empty.hidden = count > 0;
}

function renderProducts() {
  const products = filteredProducts();
  elements.result.textContent = `${products.length} 件`;
  elements.grid.innerHTML = products.map(productCard).join('');
  elements.empty.hidden = products.length > 0;
}

function updateStats() {
  const products = [...state.products.values()].filter((product) => product.active);
  const inStock = products.filter((product) => product.in_stock).length;
  const positivePrices = products.map((product) => Number(product.price)).filter((price) => price > 0);
  elements.total.textContent = products.length.toLocaleString('zh-CN');
  elements.stock.textContent = inStock.toLocaleString('zh-CN');
  elements.low.textContent = positivePrices.length ? `¥${money(Math.min(...positivePrices))}` : '—';
  elements.source.textContent = state.sources.length.toLocaleString('zh-CN');
  elements.sourceSub.textContent = `${state.sources.filter((source) => source.enabled).length} 个已启用`;
  const lastScan = Math.max(0, ...products.map((product) => Number(product.last_seen || 0)));
  elements.lastUpdate.textContent = lastScan ? `最近更新 ${dateTime(lastScan)}` : '尚未更新';
}

function setScanning(scanning, detail = '') {
  state.scanning = scanning;
  const busy = scanning || state.localScanning;
  elements.localScanButton.disabled = busy;
  elements.filteredLocalScanButton.disabled = busy;
  elements.scanPulse.classList.toggle('active', busy);
  if (!state.localScanning) {
    elements.scanText.textContent = scanning ? '扫描进行中' : '实时监听中';
    elements.scanDetail.textContent = detail || (scanning ? '商品正在逐条刷新' : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭'));
  }
}

function setLocalScanning(scanning, detail = '', label = '', target = state.localScanTarget || 'all') {
  state.localScanning = scanning;
  state.localScanTarget = scanning ? target : '';
  const busy = scanning || state.scanning;
  elements.localScanButton.disabled = busy;
  elements.filteredLocalScanButton.disabled = busy;
  elements.localScanButton.classList.toggle('scanning', scanning && target === 'all');
  elements.filteredLocalScanButton.classList.toggle('scanning', scanning && target === 'filter');
  elements.scanPulse.classList.toggle('active', busy);
  elements.localScanLabel.textContent = scanning && target === 'all' ? (label || '本地扫描中') : '本地全部扫描';
  elements.filteredScanLabel.textContent = scanning && target === 'filter' ? (label || '筛选页刷新中') : '刷新当前筛选';
  if (scanning) {
    elements.scanText.textContent = '本地扫描进行中';
    elements.scanDetail.textContent = detail || '正在使用当前设备的网络采集';
  } else if (!state.scanning) {
    elements.scanText.textContent = '实时监听中';
    elements.scanDetail.textContent = detail || (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭');
  }
}

function scheduleIncrementalRender() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  requestAnimationFrame(() => {
    let countsDirty = state.pendingRemovals.size > 0;
    for (const key of state.pendingRemovals) {
      state.products.delete(key);
      findProductCard(key)?.remove();
    }
    state.pendingRemovals.clear();
    for (const [key, update] of state.pendingProducts) {
      const isNew = !state.products.has(key);
      state.products.set(key, update.product);
      reconcileProductCard(update.product, update.change);
      if (isNew || update.change !== 'unchanged') countsDirty = true;
    }
    state.pendingProducts.clear();
    state.renderQueued = false;
    updateStats();
    if (countsDirty) updateTabCounts();
    updateVisibleSummary();
  });
}

function queueProduct(product, change = 'changed') {
  state.pendingRemovals.delete(product.goods_key);
  state.pendingProducts.set(product.goods_key, { product, change });
  scheduleIncrementalRender();
}

function queueProductRemoval(goodsKey) {
  state.pendingProducts.delete(goodsKey);
  state.pendingRemovals.add(goodsKey);
  scheduleIncrementalRender();
}

function connectEvents() {
  const stream = new EventSource('api/events');
  stream.addEventListener('open', () => {
    elements.stream.className = 'stream-status online';
    elements.stream.querySelector('span').textContent = '实时流已连接';
  });
  stream.addEventListener('error', () => {
    elements.stream.className = 'stream-status error';
    elements.stream.querySelector('span').textContent = '连接重试中';
  });
  stream.addEventListener('product', (event) => {
    const payload = JSON.parse(event.data);
    markTagsRefreshing(payload.product.tags || []);
    queueProduct(payload.product, payload.change);
  });
  stream.addEventListener('product_remove', (event) => {
    const payload = JSON.parse(event.data);
    markTagsRefreshing(state.products.get(payload.goods_key)?.tags || []);
    queueProductRemoval(payload.goods_key);
  });
  stream.addEventListener('product_refresh', (event) => {
    const payload = JSON.parse(event.data);
    applySingleProductRefresh(payload.product);
  });
  stream.addEventListener('product_refresh_remove', (event) => {
    const payload = JSON.parse(event.data);
    applySingleProductRemoval(payload.goods_key);
  });
  stream.addEventListener('scan_status', (event) => {
    const payload = JSON.parse(event.data);
    if (payload.phase === 'started') clearRefreshingTags();
    if (payload.phase === 'completed') setTimeout(clearRefreshingTags, 300);
    setScanning(Boolean(payload.scanning), scanMessage(payload));
  });
  stream.addEventListener('snapshot', (event) => {
    const payload = JSON.parse(event.data);
    state.sources = payload.sources || state.sources;
    state.stats = payload.stats || state.stats;
    renderSources();
    updateStats();
  });
  stream.addEventListener('discovery_status', (event) => {
    const payload = JSON.parse(event.data);
    if (payload.phase === 'started') {
      elements.scanDetail.textContent = '正在从公开社区发现新店铺';
    } else if (payload.phase === 'completed') {
      toast(`源发现完成：有效 ${payload.valid} 个，新增 ${payload.added} 个`);
    } else if (payload.phase === 'error') {
      toast(`源发现失败：${payload.error}`, true);
    }
  });
  stream.addEventListener('schedule_status', (event) => {
    const payload = JSON.parse(event.data);
    state.autoScanEnabled = Boolean(payload.enabled);
    state.scanIntervalMinutes = Math.max(1, Math.round(Number(payload.interval || 900) / 60));
    state.sourceInterval = Number(payload.source_interval || 15);
  });
}

function scanMessage(payload) {
  if (payload.phase === 'source_started') return `正在扫描 ${payload.token}（${payload.source_index}/${payload.source_total}）`;
  if (payload.phase === 'source_completed') return `${payload.name || payload.token}：匹配 ${payload.matched} 件`;
  if (payload.phase === 'source_error') return `${payload.token}：${payload.error}`;
  if (payload.phase === 'completed') return '本轮扫描完成';
  return payload.scanning ? '商品正在逐条刷新' : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭');
}

function renderSources() {
  if (!elements.sourceList) return;
  if (!state.sources.length) {
    elements.sourceList.innerHTML = '<div class="empty"><strong>还没有采集源</strong></div>';
    return;
  }
  elements.sourceList.innerHTML = state.sources.map((source) => {
    const statusText = { ok: '正常', error: '异常', scanning: '扫描中', pending: '待扫描' }[source.status] || source.status;
    const platform = (() => {
      try { return new URL(source.base_url || LOCAL_LDXP_BASE_URL).hostname; }
      catch { return source.base_url || 'pay.ldxp.cn'; }
    })();
    const entryText = source.entry_goods_key ? ` · 入口商品 ${source.entry_goods_key}` : '';
    return `<div class="source-item" data-token="${escapeHtml(source.token)}">
      <div class="source-name"><strong>${escapeHtml(source.name || source.token)}</strong><span>${escapeHtml(platform)} · ${escapeHtml(source.origin || '手动添加')} · ${source.product_count || 0} 件${escapeHtml(entryText)}${source.last_error ? ` · ${escapeHtml(source.last_error)}` : ''}</span></div>
      <span class="source-status ${escapeHtml(source.status)}">${escapeHtml(statusText)}</span>
      <div class="source-actions"><button type="button" data-action="toggle">${source.enabled ? '停用' : '启用'}</button><button type="button" class="danger" data-action="delete">删除</button></div>
    </div>`;
  }).join('');
}

function priceHistorySvg(history) {
  const points = [...history]
    .filter((point) => Number.isFinite(Number(point.price)))
    .sort((a, b) => Number(a.recorded_at) - Number(b.recorded_at));
  if (!points.length) return '<div class="history-empty">暂无价格节点，等待下一次成功刷新。</div>';

  const width = 760, height = 280;
  const margin = { left: 58, right: 20, top: 20, bottom: 40 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const prices = points.map((point) => Number(point.price));
  let minimum = Math.min(...prices), maximum = Math.max(...prices);
  const padding = Math.max((maximum - minimum) * .12, maximum * .03, .5);
  minimum = Math.max(0, minimum - padding);
  maximum += padding;
  const range = Math.max(.01, maximum - minimum);
  const x = (index) => points.length === 1 ? margin.left + chartWidth / 2 : margin.left + index * chartWidth / (points.length - 1);
  const y = (price) => margin.top + (maximum - price) * chartHeight / range;
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(2)} ${y(Number(point.price)).toFixed(2)}`).join(' ');
  const area = `${path} L ${x(points.length - 1).toFixed(2)} ${margin.top + chartHeight} L ${x(0).toFixed(2)} ${margin.top + chartHeight} Z`;
  const grids = Array.from({ length: 5 }, (_, index) => {
    const value = maximum - index * range / 4;
    const lineY = margin.top + index * chartHeight / 4;
    return `<line x1="${margin.left}" y1="${lineY}" x2="${width - margin.right}" y2="${lineY}"/><text x="${margin.left - 9}" y="${lineY + 4}" text-anchor="end">¥${money(value)}</text>`;
  }).join('');
  const circles = points.map((point, index) => `<circle cx="${x(index)}" cy="${y(Number(point.price))}" r="3"><title>${escapeHtml(dateTime(point.recorded_at))} · ¥${money(point.price)} · 库存 ${escapeHtml(point.stock_count)}</title></circle>`).join('');
  const firstTime = dateTime(points[0].recorded_at);
  const lastTime = dateTime(points[points.length - 1].recorded_at);
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="价格随刷新时间变化的折线图">
    <g class="chart-grid">${grids}</g><path class="chart-area" d="${area}"/><path class="chart-line" d="${path}"/><g class="chart-points">${circles}</g>
    <text class="chart-time" x="${margin.left}" y="${height - 12}">${escapeHtml(firstTime)}</text>
    <text class="chart-time" x="${width - margin.right}" y="${height - 12}" text-anchor="end">${escapeHtml(lastTime)}</text>
  </svg>`;
}

async function openPriceHistory(goodsKey) {
  const product = state.products.get(goodsKey);
  if (!product) return;
  elements.historyTitle.textContent = product.name;
  elements.historyShop.textContent = product.source_name || product.source_token;
  elements.historyToken.textContent = product.source_token;
  elements.historySummary.innerHTML = '';
  elements.historyChart.innerHTML = '<p>正在加载价格节点…</p>';
  if (!elements.historyDialog.open) elements.historyDialog.showModal();
  try {
    const payload = await api(`api/history/${encodeURIComponent(goodsKey)}`);
    const history = payload.history || [];
    const prices = history.map((point) => Number(point.price)).filter(Number.isFinite);
    const latest = history[0] || { price: product.price, recorded_at: product.last_seen };
    const lowest = prices.length ? Math.min(...prices) : Number(product.price);
    const highest = prices.length ? Math.max(...prices) : Number(product.price);
    elements.historySummary.innerHTML = `
      <article><span>最新价</span><strong>¥${money(latest.price)}</strong></article>
      <article><span>最低价</span><strong>¥${money(lowest)}</strong></article>
      <article><span>最高价</span><strong>¥${money(highest)}</strong></article>
      <article><span>刷新节点</span><strong>${history.length}</strong></article>`;
    elements.historyChart.innerHTML = priceHistorySvg(history);
  } catch (error) {
    elements.historyChart.innerHTML = `<div class="history-empty">${escapeHtml(error.message)}</div>`;
  }
}

async function refreshProduct(goodsKey) {
  if (!goodsKey || state.refreshingProducts.has(goodsKey) || state.scanning || state.localScanning) return;
  const product = state.products.get(goodsKey);
  if (!product) return;
  setProductRefreshing(goodsKey, true);
  setLocalScanning(true, `正在用当前设备刷新 ${product.name}`, '刷新单件 1/1', 'filter');
  try {
    const result = await refreshLocalProducts([product]);
    toast(result.failed ? '本地刷新失败，请检查当前网络后重试' : '商品已通过当前设备刷新', result.failed > 0);
    await loadState();
  } catch (error) {
    toast(error.message, true);
  } finally {
    setProductRefreshing(goodsKey, false);
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'filter');
  }
}

const LOCAL_LDXP_BASE_URL = 'https://pay.ldxp.cn';
const LOCAL_GOODS_TYPES = ['card', 'article', 'resource', 'equity'];
const LOCAL_PAGE_SIZE = 300;
const LOCAL_MAX_PAGES = 20;

function sourceBaseUrl(source) {
  return String(source?.base_url || LOCAL_LDXP_BASE_URL).replace(/\/$/, '');
}

function sourceRemoteToken(source) {
  return String(source?.remote_token || source?.token || '');
}

async function localMarketplacePost(baseUrl, path, fields) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  let response;
  try {
    response = await fetch(`${String(baseUrl).replace(/\/$/, '')}${path}`, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
      headers: { Accept: 'application/json, text/plain, */*' },
      body: new URLSearchParams(Object.entries(fields).map(([key, value]) => [key, value ?? ''])),
      signal: controller.signal,
    });
  } catch (error) {
    const reason = error.name === 'AbortError' ? '请求超时' : '本机网络或浏览器跨域拦截';
    throw new Error(`${reason}：${error.message}`);
  } finally {
    clearTimeout(timeout);
  }

  const text = await response.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    throw new Error(`采集站点未返回 JSON（HTTP ${response.status}）`);
  }
  if (!response.ok) throw new Error(payload.msg || `采集站点请求失败 (${response.status})`);
  if (payload.code !== 1) throw new Error(payload.msg || '采集站点返回未知错误');
  return payload.data;
}

function compactLocalItem(item, goodsType) {
  const text = (value, limit) => String(value ?? '').slice(0, limit);
  return {
    goods_key: text(item.goods_key, 200),
    name: text(item.name, 500),
    price: item.price,
    market_price: item.market_price,
    extend: { stock_count: item.extend?.stock_count },
    category: { name: text(item.category?.name, 300) },
    goods_type: text(item.goods_type || goodsType, 50),
    link: text(item.link, 2000),
    image: text(item.image, 2000),
    description: text(item.description, 1000),
    create_time: item.create_time,
  };
}

async function collectLocalSource(source) {
  const baseUrl = sourceBaseUrl(source);
  const remoteToken = sourceRemoteToken(source);
  const shop = await localMarketplacePost(baseUrl, '/shopApi/Shop/info', { token: remoteToken });
  let goodsTypes = LOCAL_GOODS_TYPES.filter((type) => Number(shop?.[`${type}_count`] || 0) > 0);
  if (!goodsTypes.length) goodsTypes = [...LOCAL_GOODS_TYPES];

  const items = new Map();
  for (const goodsType of goodsTypes) {
    for (let page = 1; page <= LOCAL_MAX_PAGES; page += 1) {
      const payload = await localMarketplacePost(baseUrl, '/shopApi/Shop/goodsList', {
        token: remoteToken,
        keywords: '',
        category_id: 0,
        goods_type: goodsType,
        current: page,
        pageSize: LOCAL_PAGE_SIZE,
      });
      const pageItems = Array.isArray(payload?.list) ? payload.list : [];
      for (const item of pageItems) {
        const compact = compactLocalItem(item, goodsType);
        if (compact.goods_key) items.set(compact.goods_key, compact);
      }
      const total = Number(payload?.total ?? pageItems.length);
      if (!pageItems.length || page * LOCAL_PAGE_SIZE >= total || pageItems.length < LOCAL_PAGE_SIZE) break;
      if (page === LOCAL_MAX_PAGES) throw new Error(`商品超过 ${LOCAL_PAGE_SIZE * LOCAL_MAX_PAGES} 条，本轮未覆盖全部数据`);
    }
  }
  const entryGoodsKey = String(source.entry_goods_key || '').trim();
  if (entryGoodsKey && !items.has(entryGoodsKey)) {
    const item = await localMarketplacePost(
      baseUrl,
      '/shopApi/Shop/goodsInfo',
      { goods_key: entryGoodsKey },
    );
    const compact = compactLocalItem(item, item?.goods_type || '');
    if (compact.goods_key) items.set(compact.goods_key, compact);
  }
  return {
    sourceName: String(shop?.nickname || source.name || source.token).slice(0, 200),
    items: [...items.values()],
  };
}

function groupLocalProducts(products) {
  const sources = new Map();
  for (const product of products) {
    if (!product?.source_token || !product?.goods_key) continue;
    if (!sources.has(product.source_token)) {
      const configuredSource = state.sources.find((item) => item.token === product.source_token);
      sources.set(product.source_token, {
        token: product.source_token,
        sourceName: product.source_name || product.source_token,
        baseUrl: sourceBaseUrl(configuredSource),
        remoteToken: sourceRemoteToken(configuredSource) || product.source_token,
        entryGoodsKey: String(configuredSource?.entry_goods_key || ''),
        types: new Map(),
        untyped: [],
      });
    }
    const source = sources.get(product.source_token);
    const goodsType = String(product.goods_type || '').trim();
    if (!goodsType) {
      source.untyped.push(product);
      continue;
    }
    if (!source.types.has(goodsType)) source.types.set(goodsType, []);
    source.types.get(goodsType).push(product);
  }
  return [...sources.values()];
}

async function collectLocalProductGroup(source, goodsType, products) {
  const targets = new Set(products.map((product) => String(product.goods_key)));
  const found = new Map();
  for (let page = 1; page <= LOCAL_MAX_PAGES; page += 1) {
    const payload = await localMarketplacePost(source.baseUrl, '/shopApi/Shop/goodsList', {
      token: source.remoteToken,
      keywords: '',
      category_id: 0,
      goods_type: goodsType,
      current: page,
      pageSize: LOCAL_PAGE_SIZE,
    });
    const pageItems = Array.isArray(payload?.list) ? payload.list : [];
    for (const item of pageItems) {
      const goodsKey = String(item?.goods_key || '');
      if (targets.has(goodsKey)) found.set(goodsKey, compactLocalItem(item, goodsType));
    }
    const total = Number(payload?.total ?? pageItems.length);
    if (!pageItems.length || page * LOCAL_PAGE_SIZE >= total || pageItems.length < LOCAL_PAGE_SIZE) break;
    if (page === LOCAL_MAX_PAGES) throw new Error(`商品超过 ${LOCAL_PAGE_SIZE * LOCAL_MAX_PAGES} 条，未安全覆盖 ${goodsType}`);
  }
  if (targets.has(source.entryGoodsKey) && !found.has(source.entryGoodsKey)) {
    const item = await localMarketplacePost(
      source.baseUrl,
      '/shopApi/Shop/goodsInfo',
      { goods_key: source.entryGoodsKey },
    );
    if (item?.goods_key) {
      found.set(String(item.goods_key), compactLocalItem(item, item.goods_type || goodsType));
    }
  }
  return { requestedKeys: [...targets], items: [...found.values()] };
}

async function collectLocalUntypedProducts(products) {
  const requestedKeys = [];
  const items = [];
  let failed = 0;
  for (const product of products) {
    try {
      const source = state.sources.find((value) => value.token === product.source_token);
      const item = await localMarketplacePost(
        sourceBaseUrl(source),
        '/shopApi/Shop/goodsInfo',
        { goods_key: product.goods_key },
      );
      requestedKeys.push(product.goods_key);
      if (item?.goods_key) items.push(compactLocalItem(item, item.goods_type || ''));
    } catch (error) {
      failed += 1;
      console.warn(`Local product refresh failed for ${product.goods_key}:`, error);
    }
  }
  return { requestedKeys, items, failed };
}

async function refreshLocalProducts(products, onProgress = null) {
  const sources = groupLocalProducts(products);
  let completed = 0;
  let failed = 0;
  let matched = 0;
  let requested = 0;

  for (let sourceIndex = 0; sourceIndex < sources.length; sourceIndex += 1) {
    const source = sources[sourceIndex];
    onProgress?.(source, sourceIndex + 1, sources.length);
    const requestedKeys = new Set();
    const items = new Map();

    for (const [goodsType, groupProducts] of source.types) {
      try {
        const group = await collectLocalProductGroup(source, goodsType, groupProducts);
        for (const key of group.requestedKeys) requestedKeys.add(key);
        for (const item of group.items) items.set(item.goods_key, item);
      } catch (error) {
        failed += 1;
        console.warn(`Local filtered scan failed for ${source.token}/${goodsType}:`, error);
      }
    }

    if (source.untyped.length) {
      const group = await collectLocalUntypedProducts(source.untyped);
      for (const key of group.requestedKeys) requestedKeys.add(key);
      for (const item of group.items) items.set(item.goods_key, item);
      failed += group.failed;
    }

    if (!requestedKeys.size) continue;
    try {
      const result = await api('api/local-scan/products', {
        method: 'POST',
        body: JSON.stringify({
          token: source.token,
          source_name: source.sourceName,
          items: [...items.values()],
          requested_keys: [...requestedKeys],
        }),
      });
      completed += 1;
      matched += Number(result.matched || 0);
      requested += requestedKeys.size;
    } catch (error) {
      failed += 1;
      console.warn(`Local filtered upload failed for ${source.token}:`, error);
    }
  }
  return { completed, failed, matched, requested };
}

async function localFilteredScan() {
  if (state.scanning || state.localScanning) return;
  const products = filteredProducts();
  if (!products.length) {
    toast('当前筛选没有可刷新的商品', true);
    return;
  }

  setLocalScanning(true, `准备刷新当前筛选的 ${products.length} 件商品`, '筛选刷新 0%', 'filter');
  try {
    const result = await refreshLocalProducts(products, (source, current, total) => {
      setLocalScanning(
        true,
        `正在用当前设备刷新 ${source.sourceName}`,
        `筛选刷新 ${current}/${total}`,
        'filter',
      );
    });
    toast(`当前筛选刷新完成：提交 ${result.requested} 件，匹配 ${result.matched} 件，失败 ${result.failed} 组`, result.failed > 0);
  } finally {
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'filter');
    await loadState();
  }
}

async function localManualScan() {
  if (state.scanning || state.localScanning) return;
  const sources = state.sources.filter((source) => source.enabled);
  if (!sources.length) {
    toast('没有已启用的采集源', true);
    return;
  }

  let succeeded = 0;
  let failed = 0;
  let matched = 0;
  setLocalScanning(true, '准备使用当前设备的网络', `本地扫描 0/${sources.length}`, 'all');
  try {
    for (let index = 0; index < sources.length; index += 1) {
      const source = sources[index];
      setLocalScanning(true, `正在本地扫描 ${source.name || source.token}`, `本地扫描 ${index + 1}/${sources.length}`, 'all');
      try {
        const collected = await collectLocalSource(source);
        const result = await api('api/local-scan/source', {
          method: 'POST',
          body: JSON.stringify({
            token: source.token,
            source_name: collected.sourceName,
            items: collected.items,
            complete: true,
          }),
        });
        succeeded += 1;
        matched += Number(result.matched || 0);
      } catch (error) {
        failed += 1;
        console.warn(`Local scan failed for ${source.token}:`, error);
      }
    }
    toast(`本地扫描完成：成功 ${succeeded} 店，失败 ${failed} 店，匹配 ${matched} 件`, failed > 0);
  } finally {
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'all');
    await loadState();
  }
}

function openSources() {
  renderSources();
  if (!elements.dialog.open) elements.dialog.showModal();
}

document.addEventListener('click', (event) => {
  const historyButton = event.target.closest('.product-history');
  if (historyButton) {
    event.preventDefault();
    event.stopPropagation();
    openPriceHistory(historyButton.closest('.product-card')?.dataset.key);
    return;
  }
  const refreshButton = event.target.closest('.product-refresh');
  if (refreshButton) {
    event.preventDefault();
    event.stopPropagation();
    refreshProduct(refreshButton.closest('.product-card')?.dataset.key);
    return;
  }
  const tab = event.target.closest('[data-category]');
  if (tab) {
    state.selectedCategory = tab.dataset.category;
    renderTabs(); renderProducts();
  }
});

$('#searchInput').addEventListener('input', (event) => { state.search = event.target.value; renderProducts(); });
$('#stockOnly').addEventListener('change', (event) => { state.stockOnly = event.target.checked; renderProducts(); });
$('#sortSelect').addEventListener('change', (event) => { state.sort = event.target.value; renderProducts(); });
elements.localScanButton.addEventListener('click', localManualScan);
elements.filteredLocalScanButton.addEventListener('click', localFilteredScan);
$('#sourceButton').addEventListener('click', () => openSources());

$('#addSourceForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await api('api/sources', {
      method: 'POST',
      body: JSON.stringify({ source: elements.sourceInput.value.trim() }),
    });
    elements.sourceInput.value = '';
    toast('采集源已加入，可使用本地扫描刷新');
    const payload = await api('api/state');
    state.sources = payload.sources || [];
    renderSources(); updateStats();
  } catch (error) { toast(error.message, true); }
});

elements.sourceList.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  const item = event.target.closest('.source-item');
  if (!button || !item) return;
  const token = item.dataset.token;
  const source = state.sources.find((value) => value.token === token);
  try {
    if (button.dataset.action === 'delete') {
      if (!confirm(`确认删除采集源 ${token}？对应的本地商品记录也会删除。`)) return;
      await api(`api/sources/${encodeURIComponent(token)}`, { method: 'DELETE' });
    } else {
      await api(`api/sources/${encodeURIComponent(token)}`, { method: 'PUT', body: JSON.stringify({ enabled: !source.enabled }) });
    }
    const payload = await api('api/state');
    state.sources = payload.sources || [];
    state.products = new Map((payload.products || []).map((product) => [product.goods_key, product]));
    renderSources(); updateStats(); renderTabs(); renderProducts();
  } catch (error) { toast(error.message, true); }
});

loadState();
connectEvents();
setInterval(() => {
  for (const card of document.querySelectorAll('.product-card .updated')) {
    const product = state.products.get(card.closest('.product-card')?.dataset.key);
    if (product) card.textContent = relativeTime(product.last_seen);
  }
}, 60000);
