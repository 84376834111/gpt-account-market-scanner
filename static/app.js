const state = {
  products: new Map(),
  productTotal: 0,
  nextProductOffset: 0,
  hasMoreProducts: true,
  productLoading: false,
  productRequestId: 0,
  productLoadLimit: 12,
  productsInitialized: false,
  catalogRevision: 0,
  completedFilterKey: '',
  streamedProducts: [],
  streamRenderQueued: false,
  sources: [],
  categories: [],
  stats: {},
  selectedCategory: 'all',
  search: '',
  searchSourceToken: '',
  stockOnly: true,
  minPrice: 0,
  maxPrice: null,
  includeMinPrice: false,
  sort: 'price',
  scanning: false,
  scanTask: { running: false, reason: '', current_source: '', pending_sources: 0 },
  sponsoredUpdate: { total: 0, completed: 0, pending: 0, running: false, next_position: 0, current_token: '', last_error: '' },
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
  history: [],
  historyMode: 'price',
  historyGranularity: 'hour',
  adminVerified: false,
  serverFullScanStarting: false,
  proxyOnlyScanStarting: false,
  proxyOnlyScanning: false,
  priceaiSyncStarting: false,
  priceaiSyncing: false,
  submittedSourceToken: '',
  commentPreviews: new Map(),
  commentCarouselIndex: new Map(),
  commentMetrics: new Map(),
  ratingSort: false,
  commentDrawer: { goodsKey: '', comments: new Map(), images: [], quickImages: [], avatar: null },
  locallyValidatedProducts: new Set(),
  localValidationRunning: false,
  localValidationTimer: 0,
};
const commentVoterKey = (() => { const existing = localStorage.getItem('ldxp-comment-voter'); if (existing) return existing; const key = crypto.randomUUID?.() || `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`; localStorage.setItem('ldxp-comment-voter', key); return key; })();

const $ = (selector) => document.querySelector(selector);
let searchReloadTimer = 0;
let nextLocalRequestAt = 0;
const LOCAL_REQUEST_COOLDOWN_MS = 0;
const PRODUCT_CACHE_TTL_MS = 30 * 60_000;
const REGULAR_USER_REFRESH_LIMIT = 24;
const elements = {
  grid: $('#productGrid'), empty: $('#emptyState'), tabs: $('#categoryTabs'),
  total: $('#totalStat'), stock: $('#stockStat'), low: $('#lowStat'), source: $('#sourceStat'),
  sourceSub: $('#sourceStatSub'), result: $('#resultCount'), lastUpdate: $('#lastUpdate'),
  scanPulse: $('#scanPulse'), scanText: $('#scanStateText'),
  localScanButton: $('#localScanButton'), localScanLabel: $('#localScanButton .local-scan-label'),
  browserFactoryButton: $('#browserFactoryButton'), browserFactoryLabel: $('#browserFactoryButton .browser-factory-label'),
  browserFactoryMultiplier: $('#browserFactoryMultiplier'),
  browserFactoryStatus: $('#browserFactoryStatus'),
  refreshOutOfStockButton: $('#refreshOutOfStockButton'),
  refreshOffShelfButton: $('#refreshOffShelfButton'),
  retryErrorSourcesButton: $('#retryErrorSourcesButton'),
  adminTokenInput: $('#adminTokenInput'), adminTokenVerifyButton: $('#adminTokenVerifyButton'),
  adminFullScanButton: $('#adminFullScanButton'),
  sponsoredUpdateButton: $('#sponsoredUpdateButton'),
  adminProxyScanButton: $('#adminProxyScanButton'),
  priceaiSyncButton: $('#priceaiSyncButton'),
  scanDetail: $('#scanDetail'), stream: $('#streamStatus'), dialog: $('#sourceDialog'),
  sourceList: $('#sourceList'), sourceInput: $('#sourceInput'), toast: $('#toast'),
  historyDialog: $('#historyDialog'), historyTitle: $('#historyTitle'), historyShop: $('#historyShop'),
  historyToken: $('#historyToken'), historySummary: $('#historySummary'), historyChart: $('#historyChart'),
  historyModes: $('#historyModes'), historyGranularity: $('#historyGranularity'),
  priceMin: $('#priceMin'), priceMax: $('#priceMax'), includeMinPrice: $('#includeMinPrice'),
  loadMore: $('#loadMoreProducts'), loadMoreButton: $('#loadMoreButton'),
  loadBatchSize: $('#loadBatchSize'), loadMoreStatus: $('#loadMoreStatus'),
  sourceImportProgress: $('#sourceImportProgress'), sourceImportProgressText: $('#sourceImportProgressText'),
  ratingSort: $('#ratingSort'), commentDialog: $('#commentDialog'), commentDialogTitle: $('#commentDialogTitle'),
  commentDialogProduct: $('#commentDialogProduct'), commentMetric: $('#commentMetric'), commentRefreshButton: $('#commentRefreshButton'),
  commentCloseButton: $('#commentCloseButton'), drawerCommentList: $('#drawerCommentList'), drawerCommentForm: $('#drawerCommentForm'),
  drawerAdminToken: $('#drawerAdminToken'), drawerAdminVerify: $('#drawerAdminVerify'), drawerAdminState: $('#drawerAdminState'),
  drawerCommentAuthor: $('#drawerCommentAuthor'), drawerCommentBody: $('#drawerCommentBody'), drawerCommentAvatar: $('#drawerCommentAvatar'), drawerAvatarPreview: $('#drawerAvatarPreview'), drawerCommentImages: $('#drawerCommentImages'), drawerImagePreview: $('#drawerImagePreview'),
  quickCommentDialog: $('#quickCommentDialog'), quickCommentForm: $('#quickCommentForm'), quickCommentBody: $('#quickCommentBody'), quickCommentImages: $('#quickCommentImages'), quickImagePreview: $('#quickImagePreview'),
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

function setSourceImportProgress(token, message, status = 'running') {
  if (!elements.sourceImportProgress || !elements.sourceImportProgressText) return;
  if (token) state.submittedSourceToken = token;
  elements.sourceImportProgress.hidden = false;
  elements.sourceImportProgress.dataset.status = status;
  elements.sourceImportProgressText.textContent = message;
  clearTimeout(setSourceImportProgress.timer);
  if (status === 'done' || status === 'error') {
    setSourceImportProgress.timer = setTimeout(() => {
      elements.sourceImportProgress.hidden = true;
      state.submittedSourceToken = '';
    }, 5000);
  }
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
  const initialLoad = !state.productsInitialized;
  if (initialLoad) {
    state.productsInitialized = true;
    // Start rendering the first product batch without waiting for the dashboard snapshot.
    void reloadProducts();
  }
  try {
    const renderedCatalogRevision = state.catalogRevision;
    const payload = await api('api/state');
    state.sources = payload.sources || [];
    state.categories = payload.categories || [];
    state.stats = payload.stats || {};
    state.catalogRevision = Number(payload.catalog_revision || 0);
    state.scanning = Boolean(payload.scanning);
    state.scanTask = payload.scan_task || { running: state.scanning };
    state.sponsoredUpdate = payload.sponsored_update || state.sponsoredUpdate;
    state.autoScanEnabled = Boolean(payload.auto_scan_enabled);
    state.scanIntervalMinutes = Math.max(1, Math.round(Number(payload.scan_interval || 900) / 60));
    state.sourceInterval = Number(payload.source_interval || 15);
    updateStats();
    renderTabs();
    renderSources();
    if (!initialLoad) {
      await reloadProducts();
    } else if (renderedCatalogRevision && renderedCatalogRevision !== state.catalogRevision) {
      // A cache from before a source scan must not keep displaying an empty result set.
      void reloadProducts();
    }
    setScanning(state.scanning, state.scanning ? '正在采集公开店铺' : '自动扫描已关闭');
  } catch (error) {
    toast(error.message, true);
    elements.empty.hidden = false;
  }
}

function categoryCounts() {
  return state.stats.category_counts || {};
}

function categoryStockCounts() {
  return state.stats.category_stock_counts || {};
}

function categoryOffShelfCounts() {
  return state.stats.category_off_shelf_counts || {};
}

function renderTabs() {
  const counts = categoryCounts();
  const stockCounts = categoryStockCounts();
  const offShelfCounts = categoryOffShelfCounts();
  const tabs = [
    { key: 'all', label: '全部', count: Number(state.stats.total || 0), stockCount: Number(state.stats.in_stock || 0), offShelfCount: Number(state.stats.active_catalog_off_shelf || 0) },
    ...state.categories.map((item) => ({ ...item, count: counts[item.key] || 0, stockCount: stockCounts[item.key] || 0, offShelfCount: offShelfCounts[item.key] || 0 })),
  ];
  elements.tabs.innerHTML = tabs.map((tab) => `
    <span class="category-control">
      <button type="button" class="category ${state.selectedCategory === tab.key ? 'active' : ''} ${state.refreshingTags.has(tab.key) ? 'refreshing' : ''}" data-category="${escapeHtml(tab.key)}" role="tab" aria-selected="${state.selectedCategory === tab.key}" aria-busy="${state.refreshingTags.has(tab.key)}">
        ${escapeHtml(tab.label)}
        <span class="category-count category-count-total">总 ${tab.count}</span>
        <span class="category-count category-count-stock">有货 ${tab.stockCount}</span>
        <span class="category-count category-count-off-shelf">下架 ${tab.offShelfCount}</span>
        <i class="refresh-indicator" title="正在刷新" aria-hidden="true"></i>
      </button>
      <button type="button" class="category-refresh" data-refresh-category="${escapeHtml(tab.key)}" title="用当前网络刷新 ${escapeHtml(tab.label)}" aria-label="用当前网络刷新 ${escapeHtml(tab.label)}" ${state.localScanning ? 'disabled' : ''}>↻</button>
    </span>`).join('');
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
  const stockCounts = categoryStockCounts();
  const offShelfCounts = categoryOffShelfCounts();
  for (const tab of elements.tabs.querySelectorAll('[data-category]')) {
    const key = tab.dataset.category;
    const count = key === 'all' ? Number(state.stats.total || 0) : (counts[key] || 0);
    const stockCount = key === 'all' ? Number(state.stats.in_stock || 0) : (stockCounts[key] || 0);
    const offShelfCount = key === 'all' ? Number(state.stats.active_catalog_off_shelf || 0) : (offShelfCounts[key] || 0);
    const totalBadge = tab.querySelector('.category-count-total');
    const stockBadge = tab.querySelector('.category-count-stock');
    const offShelfBadge = tab.querySelector('.category-count-off-shelf');
    if (totalBadge && totalBadge.textContent !== `总 ${count}`) totalBadge.textContent = `总 ${count}`;
    if (stockBadge && stockBadge.textContent !== `有货 ${stockCount}`) stockBadge.textContent = `有货 ${stockCount}`;
    if (offShelfBadge && offShelfBadge.textContent !== `下架 ${offShelfCount}`) offShelfBadge.textContent = `下架 ${offShelfCount}`;
  }
}

function productMatchesFilters(product) {
  if (!product?.active) return false;
  if (state.selectedCategory === 'platform_banned') {
    if (!product.platform_banned) return false;
  } else if (state.selectedCategory === 'off_shelf') {
    if (!product.off_shelf) return false;
  } else {
    if (product.off_shelf || product.platform_banned) return false;
    if (state.selectedCategory !== 'all' && !(product.tags || []).includes(state.selectedCategory)) return false;
  }
  if (state.stockOnly && !['off_shelf', 'platform_banned'].includes(state.selectedCategory) && !product.in_stock) return false;
  const price = Number(product.price);
  if (!Number.isFinite(price)) return false;
  if (state.includeMinPrice ? price < state.minPrice : price <= state.minPrice) return false;
  if (state.maxPrice !== null && price > state.maxPrice) return false;
  const query = state.search.trim().toLocaleLowerCase();
  if (state.searchSourceToken) return product.source_token === state.searchSourceToken;
  return !query || `${product.name} ${product.source_name} ${product.category_name} ${product.link} ${product.goods_key}`.toLocaleLowerCase().includes(query);
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

function currentProductQuery(limit, offset) {
  return new URLSearchParams({
    category: state.selectedCategory,
    stock_only: ['off_shelf', 'platform_banned'].includes(state.selectedCategory) ? '0' : (state.stockOnly ? '1' : '0'),
    min_price: String(state.minPrice),
    max_price: state.maxPrice === null ? '' : String(state.maxPrice),
    include_min: state.includeMinPrice ? '1' : '0',
    search: state.search.trim(),
    sort: state.sort,
    rating_sort: state.ratingSort ? '1' : '0',
    limit: String(limit),
    offset: String(offset),
  });
}

function currentUserRefreshScope() {
  return {
    category: state.selectedCategory,
    stock_only: ['off_shelf', 'platform_banned'].includes(state.selectedCategory) ? false : state.stockOnly,
    min_price: state.minPrice,
    max_price: state.maxPrice,
    include_left: state.includeMinPrice,
    search: state.search.trim(),
    sort: state.sort,
    rating_sort: state.ratingSort,
  };
}

function currentFilterMappingKey() {
  return JSON.stringify({
    category: state.selectedCategory,
    stock_only: state.stockOnly,
    min_price: state.minPrice,
    max_price: state.maxPrice,
    include_min: state.includeMinPrice,
    search: state.search.trim().toLocaleLowerCase(),
  });
}

function isMarketplaceLinkSearch(value) {
  try {
    const url = new URL(String(value || '').trim());
    return ['pay.ldxp.cn', 'www.ldxp.cn', 'catfk.com', 'www.catfk.com'].includes(url.hostname)
      && /^\/(shop|item)\//i.test(url.pathname);
  } catch {
    return false;
  }
}

function searchTargetsSource(value, sourceToken) {
  try {
    const url = new URL(String(value || '').trim());
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length < 2 || parts.at(-2)?.toLowerCase() !== 'shop') return false;
    const remoteToken = decodeURIComponent(parts.at(-1) || '');
    const sourceKey = ['catfk.com', 'www.catfk.com'].includes(url.hostname)
      ? `catfk.com:${remoteToken}`
      : remoteToken;
    return sourceKey === sourceToken;
  } catch {
    return false;
  }
}

async function readProductStream(params, onRecord) {
  const response = await fetch(`api/products/stream?${params.toString()}`, { cache: 'no-store' });
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch { /* proxy errors may not be json */ }
    throw new Error(payload.error || `请求失败 (${response.status})`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('当前浏览器不支持商品流式加载');
  const decoder = new TextDecoder();
  let buffered = '';
  const consume = (final = false) => {
    const lines = buffered.split('\n');
    buffered = final ? '' : lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      onRecord(JSON.parse(line));
    }
    if (final && buffered.trim()) onRecord(JSON.parse(buffered));
  };

  while (true) {
    const { value, done } = await reader.read();
    if (value) {
      buffered += decoder.decode(value, { stream: !done });
      consume(false);
    }
    if (done) break;
  }
  buffered += decoder.decode();
  consume(true);
}

function updateProductLoadingControls() {
  const loaded = state.products.size;
  const total = Number(state.productTotal || 0);
  elements.result.textContent = total ? `已显示 ${loaded} / ${total} 件` : (state.productLoading ? '正在加载…' : '0 件');
  elements.empty.hidden = state.productLoading || total > 0;
  elements.loadMore.hidden = !state.productLoading && !state.hasMoreProducts;
  elements.loadMoreButton.disabled = state.productLoading || !state.hasMoreProducts;
  elements.loadMoreStatus.textContent = state.productLoading
    ? '正在从服务器加载…'
    : state.hasMoreProducts
      ? `还有 ${Math.max(0, total - loaded)} 件可继续加载`
      : `已显示全部 ${total} 件`;
}

function flushStreamedProducts() {
  state.streamRenderQueued = false;
  if (!state.streamedProducts.length) return;
  const fragment = document.createDocumentFragment();
  for (const product of state.streamedProducts.splice(0)) {
    state.products.set(product.goods_key, product);
    const card = findProductCard(product.goods_key);
    if (card) {
      updateProductCard(card, product);
      positionProductCard(card, product);
    } else if (productMatchesFilters(product)) {
      fragment.appendChild(createProductCard(product));
    }
  }
  elements.grid.appendChild(fragment);
  void loadCommentPreviews([...elements.grid.children].map((card) => card.dataset.key));
  void validateVisibleProductsLocally([...elements.grid.children].map((card) => card.dataset.key));
  updateProductLoadingControls();
}

function queueStreamedProduct(product) {
  state.streamedProducts.push(product);
  if (state.streamRenderQueued) return;
  state.streamRenderQueued = true;
  requestAnimationFrame(flushStreamedProducts);
}

function productCacheKey(params) {
  return `ldxp-product-stream:${params.toString()}`;
}

function readCachedProductPage(params) {
  try {
    const cached = JSON.parse(localStorage.getItem(productCacheKey(params)) || 'null');
    return cached
      && Array.isArray(cached.records)
      ? cached.records
      : null;
  } catch {
    return null;
  }
}

async function refreshVisibleProducts(keys, requestId) {
  if (!keys.length) return;
  const params = new URLSearchParams();
  keys.forEach((key) => params.append('key', key));
  try {
    const payload = await api(`api/products/visible?${params.toString()}`);
    if (requestId !== state.productRequestId) return;
    const fresh = new Map((payload.products || []).map((product) => [product.goods_key, product]));
    for (const key of keys) {
      const product = fresh.get(key);
      if (product) {
        state.products.set(key, product);
        reconcileProductCard(product, 'changed');
      } else {
        applySingleProductRemoval(key);
      }
    }
    state.catalogRevision = Number(payload.catalog_revision || state.catalogRevision);
    updateProductLoadingControls();
  } catch {
    // Cached cards remain usable when the background refresh cannot complete.
  }
}

function cacheProductPage(params, records) {
  try {
    localStorage.setItem(productCacheKey(params), JSON.stringify({
      expires_at: Date.now() + PRODUCT_CACHE_TTL_MS,
      catalog_revision: state.catalogRevision,
      records,
    }));
  } catch {
    // Storage can be unavailable in private mode; the live request still works.
  }
}

function applyProductStreamRecord(record, requestId, offset) {
  if (requestId !== state.productRequestId) return;
  if (record.type === 'meta') {
    state.productTotal = Number(record.total || 0);
    state.catalogRevision = Number(record.catalog_revision || state.catalogRevision);
    state.nextProductOffset = Number(record.next_offset || offset);
    state.hasMoreProducts = Boolean(record.has_more);
    state.searchSourceToken = String(record.search_source_token || '');
    if (!state.hasMoreProducts) state.completedFilterKey = currentFilterMappingKey();
  } else if (record.type === 'product' && record.product) {
    queueStreamedProduct(record.product);
  }
}

async function loadProductBatch() {
  if (state.productLoading || !state.hasMoreProducts) return;
  const requestId = state.productRequestId;
  const offset = state.nextProductOffset;
  const query = currentProductQuery(state.productLoadLimit, offset);
  state.productLoading = true;
  updateProductLoadingControls();
  try {
    const cached = readCachedProductPage(query);
    const cachedMeta = cached?.find((record) => record.type === 'meta');
    const cachedRevision = Number(cachedMeta?.catalog_revision || 0);
    const hasSearch = Boolean(state.search.trim());
    if (cached && !hasSearch && (!state.catalogRevision || cachedRevision === state.catalogRevision)) {
      cached.forEach((record) => applyProductStreamRecord(record, requestId, offset));
      if (state.streamRenderQueued) flushStreamedProducts();
      const visibleKeys = cached
        .filter((record) => record.type === 'product' && record.product)
        .map((record) => record.product.goods_key);
      void refreshVisibleProducts(visibleKeys, requestId);
    } else {
      const records = [];
      await readProductStream(query, (record) => {
        if (record.type !== 'end') records.push(record);
        applyProductStreamRecord(record, requestId, offset);
      });
      if (requestId === state.productRequestId) cacheProductPage(query, records);
    }
  } catch (error) {
    if (requestId === state.productRequestId) toast(error.message, true);
  } finally {
    if (requestId === state.productRequestId) {
      state.productLoading = false;
      if (state.streamRenderQueued) flushStreamedProducts();
      updateProductLoadingControls();
    }
  }
}

async function reloadProducts() {
  state.productRequestId += 1;
  state.products.clear();
  state.productTotal = 0;
  state.nextProductOffset = 0;
  state.hasMoreProducts = true;
  state.completedFilterKey = '';
  state.searchSourceToken = '';
  state.productLoading = false;
  state.streamedProducts = [];
  elements.grid.replaceChildren();
  updateProductLoadingControls();
  await loadProductBatch();
}

function sortCompletedFilterMapping() {
  const products = [...state.products.values()].sort(compareProducts);
  const fragment = document.createDocumentFragment();
  for (const product of products) fragment.appendChild(createProductCard(product));
  elements.grid.replaceChildren(fragment);
  void loadCommentPreviews(products.map((product) => product.goods_key));
  void validateVisibleProductsLocally(products.map((product) => product.goods_key));
  updateVisibleSummary();
}

function productTags(product) {
  const labels = new Map(state.categories.map((category) => [category.key, category.label]));
  const tagHtml = (product.tags || []).map((tag) => `<span class="tag">${escapeHtml(labels.get(tag) || tag)}</span>`).join('');
  const stockClass = product.in_stock ? 'stock' : 'out';
  const stockLabel = product.off_shelf ? '已下架' : product.stock_count < 0 ? '库存未知' : product.in_stock ? `库存 ${product.stock_count}` : '已缺货';
  const lazy = !product.off_shelf && (Boolean(product.platform_banned) || (Number(product.stock_count) === 0
    && Number(product.out_of_stock_since || 0) > 0
    && Date.now() / 1000 - Number(product.out_of_stock_since) >= 24 * 60 * 60));
  return `${tagHtml}<span class="tag ${stockClass}">${stockLabel}</span>${lazy ? '<span class="tag lazy-refresh" title="连续缺货满一天的商品由服务器每日复查">极懒更新 · 每日</span>' : ''}`;
}

function marketPrice(product) {
  return Number(product.market_price) > Number(product.price)
    ? `<div class="market-price">参考 ¥${money(product.market_price)}</div>` : '';
}

function commentPreviewHtml(goodsKey) {
  const comments = state.commentPreviews.get(goodsKey) || [];
  if (!comments.length) return '<span class="comment-preview-empty">暂无评论，等待评论…</span>';
  const index = state.commentCarouselIndex.get(goodsKey) || 0;
  const comment = comments[index % comments.length];
  const text = String(comment.body || '').trim() || '图片评论';
  const image = comment.images?.[0]
    ? `<img class="comment-preview-image" src="${escapeHtml(comment.images[0])}" alt="" loading="lazy">` : '';
  return `${image}<span class="comment-preview-label">评论${comments.length > 1 ? ` ${index % comments.length + 1}/${comments.length}` : ''}</span><span class="comment-preview-text">${escapeHtml(text)}</span><span class="comment-votes"><button type="button" data-comment-vote="1" data-comment-id="${escapeHtml(comment.id)}">👍 ${Number(comment.upvotes || 0)}</button><button type="button" data-comment-vote="-1" data-comment-id="${escapeHtml(comment.id)}">👎 ${Number(comment.downvotes || 0)}</button></span>`;
}

function updateCommentPreview(goodsKey) {
  const card = findProductCard(goodsKey);
  const preview = card?.querySelector('.comment-carousel');
  if (preview) preview.innerHTML = commentPreviewHtml(goodsKey);
}

async function loadCommentPreviews(goodsKeys) {
  const keys = [...new Set(goodsKeys)].filter(Boolean);
  if (!keys.length) return;
  const params = new URLSearchParams(); keys.forEach((key) => params.append('key', key));
  try {
    const payload = await api(`api/comments/previews?${params}`);
    Object.entries(payload.previews || {}).forEach(([key, comments]) => {
      state.commentPreviews.set(key, comments || []);
      if (!state.commentCarouselIndex.has(key)) state.commentCarouselIndex.set(key, 0);
      updateCommentPreview(key);
    });
    Object.entries(payload.metrics || {}).forEach(([key, metric]) => state.commentMetrics.set(key, metric));
  } catch (error) { console.warn('Unable to load comment previews:', error); }
}

function productCard(product, index) {
  const image = product.image
    ? `<img class="product-image" src="${escapeHtml(product.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=\'product-image fallback\'>L</span>'">`
    : '<span class="product-image fallback">L</span>';
  const refreshing = state.refreshingProducts.has(product.goods_key);
  return `<article class="product-card${refreshing ? ' product-refreshing' : ''}" data-key="${escapeHtml(product.goods_key)}">
    <a class="product-card-link" href="${escapeHtml(product.link)}" target="_blank" rel="noopener noreferrer" aria-label="查看 ${escapeHtml(product.name)}"></a>
    <button class="product-history" type="button" title="查看价格走势" aria-label="查看 ${escapeHtml(product.name)} 的价格走势"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 17 5-6 4 3 7-9"/></svg></button>
    <button class="product-refresh" type="button" title="${product.off_shelf ? '已下架商品不更新' : '只刷新这个商品'}" aria-label="只刷新 ${escapeHtml(product.name)}" aria-busy="${refreshing}" ${refreshing || product.off_shelf ? 'disabled' : ''}><span aria-hidden="true">↻</span></button>
    <div class="product-head">${image}<div class="product-title">
      <span class="product-title-link">${escapeHtml(product.name)}</span>
      <div class="shop-line">${escapeHtml(product.source_name || product.source_token)} · ${escapeHtml(product.category_name || product.goods_type)}</div>
    </div></div>
    <div class="tags"><div class="product-tag-list">${productTags(product)}</div><div class="comment-card-actions"><button type="button" class="comment-area-button">评论区</button><button type="button" class="comment-refresh-button">更新</button></div></div><div class="comment-carousel" role="button" tabindex="0" title="查看商品评论" aria-label="查看 ${escapeHtml(product.name)} 的评论">${commentPreviewHtml(product.goods_key)}</div>
    <div class="price-row"><div class="price-block"><div class="price">${money(product.price)}</div><div class="market-slot">${marketPrice(product)}</div></div>
      <div class="product-meta"><span class="stock-number">${escapeHtml(product.source_token)}</span><span class="updated">${relativeTime(product.last_seen)}</span></div>
    </div>
  </article>`;
}

function createProductCard(product) {
  const template = document.createElement('template');
  template.innerHTML = productCard(product, 0).trim();
  const card = template.content.firstElementChild;
  card.dataset.displayedAt = String(Date.now());
  return card;
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
  refreshButton.title = product.off_shelf ? '已下架商品不更新' : '只刷新这个商品';
  refreshButton.disabled = Boolean(product.off_shelf) || state.refreshingProducts.has(product.goods_key);
  card.querySelector('.product-history').setAttribute('aria-label', `查看 ${product.name} 的价格走势`);
  const shop = card.querySelector('.shop-line');
  const shopText = `${product.source_name || product.source_token} · ${product.category_name || product.goods_type}`;
  if (shop.textContent !== shopText) shop.textContent = shopText;
  card.querySelector('.product-tag-list').innerHTML = productTags(product);
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
  button.disabled = refreshing || Boolean(state.products.get(goodsKey)?.off_shelf);
  button.setAttribute('aria-busy', String(refreshing));
}

function applySingleProductRefresh(product) {
  if (!state.products.has(product.goods_key)) return;
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
  updateVisibleSummary();
}

function applySingleProductRemoval(goodsKey) {
  if (!state.products.has(goodsKey)) return;
  state.products.delete(goodsKey);
  findProductCard(goodsKey)?.remove();
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
  updateProductLoadingControls();
}

function renderProducts() {
  void reloadProducts();
}

function updateStats() {
  const stats = state.stats || {};
  elements.total.textContent = Number(stats.total || 0).toLocaleString('zh-CN');
  elements.stock.textContent = Number(stats.in_stock || 0).toLocaleString('zh-CN');
  elements.low.textContent = Number(stats.lowest_price || 0) > 0 ? `¥${money(stats.lowest_price)}` : '—';
  elements.source.textContent = state.sources.length.toLocaleString('zh-CN');
  elements.sourceSub.textContent = `${state.sources.filter((source) => source.enabled).length} 个已启用`;
  const lastScan = Number(stats.last_scan || 0);
  elements.lastUpdate.textContent = lastScan ? `最近更新 ${dateTime(lastScan)}` : '尚未更新';
}

function updateAdminProxyScanButton() {
  const taskRunning = Boolean(state.scanTask?.running || state.scanning);
  const sponsoredRunning = Boolean(state.sponsoredUpdate?.running);
  const scanBusy = state.localScanning || state.serverFullScanStarting || state.proxyOnlyScanStarting || sponsoredRunning;
  const allBusy = scanBusy || state.priceaiSyncStarting || state.priceaiSyncing;
  elements.adminTokenVerifyButton.disabled = allBusy;
  elements.adminFullScanButton.disabled = true;
  elements.adminFullScanButton.classList.toggle('scanning', taskRunning);
  elements.adminFullScanButton.textContent = '服务器全量更新 · 暂停';
  const sponsored = state.sponsoredUpdate || {};
  const sponsoredTotal = Number(sponsored.total || 0);
  const sponsoredDone = Number(sponsored.completed || 0);
  const sponsoredPosition = Number(sponsored.next_position || sponsoredDone + 1);
  elements.sponsoredUpdateButton.disabled = (state.localScanning || taskRunning) || !state.adminVerified;
  elements.sponsoredUpdateButton.classList.toggle('scanning', sponsoredRunning);
  elements.sponsoredUpdateButton.textContent = sponsoredTotal
    ? (sponsoredRunning
      ? (sponsored.stop_requested
        ? `停止中 ${Math.min(sponsoredPosition, sponsoredTotal)}/${sponsoredTotal}`
        : `停止赞助更新 ${Math.min(sponsoredPosition, sponsoredTotal)}/${sponsoredTotal}`)
      : `赞助更新 ${sponsoredDone}/${sponsoredTotal}`)
    : '赞助更新';
  elements.adminProxyScanButton.disabled = scanBusy || !state.adminVerified;
  elements.adminProxyScanButton.classList.toggle('scanning', taskRunning && state.scanTask?.reason === 'manual_proxy_only');
  elements.adminProxyScanButton.textContent = taskRunning && state.scanTask?.reason === 'manual_proxy_only'
    ? '代理扫描中'
    : '代理全量扫描';
  elements.priceaiSyncButton.disabled = state.priceaiSyncStarting || state.priceaiSyncing || !state.adminVerified;
  elements.browserFactoryButton.disabled = state.localScanning;
  elements.retryErrorSourcesButton.disabled = state.localScanning;
  elements.priceaiSyncButton.classList.toggle('scanning', state.priceaiSyncing);
  elements.priceaiSyncButton.textContent = state.priceaiSyncing ? 'PriceAI 同步中' : '同步 PriceAI';
  if (!state.localScanning) {
    elements.localScanLabel.textContent = '服务器全量更新';
  }
}

function getAdminHeaders() {
  const key = String(elements.adminTokenInput.value || '').trim();
  if (!key) {
    toast('请先输入管理员令牌', true);
    return null;
  }
  sessionStorage.setItem('ldxp-admin-key', key);
  return { 'X-LDXP-Admin-Key': key };
}

function forgetAdminKey(error) {
  if (error?.status !== 403) return;
  state.adminVerified = false;
  sessionStorage.removeItem('ldxp-admin-key');
  elements.adminTokenInput.value = '';
  renderSources();
}

async function verifyAdminToken(quiet = false) {
  const headers = getAdminHeaders();
  if (!headers) return false;
  try {
    await api('api/admin/verify', { method: 'POST', headers });
    state.adminVerified = true;
    if (!quiet) toast('管理员令牌已验证');
    return true;
  } catch (error) {
    forgetAdminKey(error);
    if (!quiet) toast(error.message, true);
    return false;
  } finally {
    updateAdminProxyScanButton();
    renderSources();
  }
}

async function startServerFullScan() {
  if (state.localScanning || state.serverFullScanStarting) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  state.serverFullScanStarting = true;
  updateAdminProxyScanButton();
  try {
    const result = await api('api/scan', { method: 'POST', headers });
    state.adminVerified = true;
    state.scanTask = result.task || state.scanTask;
    if (result.started || result.joined) {
      setScanning(true, result.message || '服务器正在流式刷新商品');
      await reloadProducts();
    }
    toast(result.message || '服务器全量扫描已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  } finally {
    state.serverFullScanStarting = false;
    updateAdminProxyScanButton();
  }
}

async function startSponsoredUpdate() {
  if (state.localScanning) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  try {
    const running = Boolean(state.sponsoredUpdate?.running);
    const result = await api(running ? 'api/sponsored-update/stop' : 'api/sponsored-update/start', { method: 'POST', headers });
    state.adminVerified = true;
    state.sponsoredUpdate = { ...state.sponsoredUpdate, ...result };
    updateAdminProxyScanButton();
    toast(result.message || '赞助更新已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  }
}

async function startAdminProxyScan() {
  if (state.localScanning || state.proxyOnlyScanStarting) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  state.proxyOnlyScanStarting = true;
  updateAdminProxyScanButton();
  try {
    const result = await api('api/scan/proxy-only', { method: 'POST', headers });
    state.adminVerified = true;
    state.scanTask = result.task || state.scanTask;
    if (result.started || result.joined) {
      setScanning(true, result.message || '服务器正在流式刷新商品');
      await reloadProducts();
    }
    toast(result.message || '服务器代理扫描已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  } finally {
    state.proxyOnlyScanStarting = false;
    updateAdminProxyScanButton();
  }
}

async function startPriceaiSync() {
  if (state.priceaiSyncStarting || state.priceaiSyncing) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  state.priceaiSyncStarting = true;
  updateAdminProxyScanButton();
  try {
    const result = await api('api/import/priceai', { method: 'POST', headers });
    state.adminVerified = true;
    toast(result.message || 'PriceAI 公开快照同步已启动');
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  } finally {
    state.priceaiSyncStarting = false;
    updateAdminProxyScanButton();
  }
}

function setScanning(scanning, detail = '') {
  state.scanning = scanning;
  const busy = scanning || state.localScanning;
  elements.localScanButton.disabled = state.localScanning;
  elements.scanPulse.classList.toggle('active', busy);
  updateAdminProxyScanButton();
  if (!state.localScanning) {
    elements.scanText.textContent = scanning ? '扫描进行中' : '实时监听中';
    elements.scanDetail.textContent = detail || (scanning ? '商品正在逐条刷新' : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭'));
  }
}

function setLocalScanning(scanning, detail = '', label = '', target = state.localScanTarget || 'all') {
  state.localScanning = scanning;
  state.localScanTarget = scanning ? target : '';
  const busy = scanning || state.scanning;
  elements.localScanButton.disabled = scanning;
  elements.refreshOutOfStockButton.disabled = scanning;
  elements.refreshOffShelfButton.disabled = scanning;
  if (elements.filteredLocalScanButton) elements.filteredLocalScanButton.disabled = scanning;
  elements.localScanButton.classList.toggle('scanning', scanning && target === 'all');
  elements.filteredLocalScanButton?.classList.toggle('scanning', scanning && target === 'filter');
  for (const button of elements.tabs.querySelectorAll('[data-refresh-category]')) button.disabled = scanning;
  elements.scanPulse.classList.toggle('active', busy);
  updateAdminProxyScanButton();
  elements.localScanLabel.textContent = scanning && target === 'all' ? (label || '本地扫描中') : '本地全部扫描';
  if (elements.filteredScanLabel) elements.filteredScanLabel.textContent = scanning && target === 'filter' ? (label || '筛选页刷新中') : '刷新当前筛选';
  if (scanning) {
    elements.scanText.textContent = '本地扫描进行中';
    elements.scanDetail.textContent = detail || '正在使用当前设备的网络采集';
  } else {
    elements.scanText.textContent = state.scanning ? '服务器扫描进行中' : '实时监听中';
    elements.scanDetail.textContent = detail || (state.scanning
      ? '服务器后台扫描继续运行'
      : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭'));
  }
}

function scheduleIncrementalRender() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  requestAnimationFrame(() => {
    for (const key of state.pendingRemovals) {
      if (!state.products.has(key)) continue;
      state.products.delete(key);
      findProductCard(key)?.remove();
      if (state.completedFilterKey === currentFilterMappingKey()) state.productTotal = Math.max(0, state.productTotal - 1);
    }
    state.pendingRemovals.clear();
    for (const [key, update] of state.pendingProducts) {
      const existed = state.products.has(key);
      const canAddToCompletedMapping = state.completedFilterKey === currentFilterMappingKey()
        && productMatchesFilters(update.product);
      if (!existed && !canAddToCompletedMapping) continue;
      if (!productMatchesFilters(update.product)) {
        state.products.delete(key);
        findProductCard(key)?.remove();
        if (existed && state.completedFilterKey === currentFilterMappingKey()) state.productTotal = Math.max(0, state.productTotal - 1);
        continue;
      }
      state.products.set(key, update.product);
      reconcileProductCard(update.product, update.change);
      if (!existed && state.completedFilterKey === currentFilterMappingKey()) state.productTotal += 1;
    }
    state.pendingProducts.clear();
    state.renderQueued = false;
    updateVisibleSummary();
  });
}

function queueProduct(product, change = 'changed') {
  const canAddToCompletedMapping = state.completedFilterKey === currentFilterMappingKey()
    && productMatchesFilters(product);
  const streamCurrentServerScan = Boolean(state.scanTask?.running) && productMatchesFilters(product);
  if (!state.products.has(product.goods_key) && !canAddToCompletedMapping && !streamCurrentServerScan) return;
  state.pendingRemovals.delete(product.goods_key);
  state.pendingProducts.set(product.goods_key, { product, change });
  scheduleIncrementalRender();
}

function queueProductRemoval(goodsKey) {
  if (!state.products.has(goodsKey)) return;
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
  stream.addEventListener('ready', (event) => {
    const payload = JSON.parse(event.data);
    state.scanning = Boolean(payload.scanning);
    state.scanTask = payload.task || state.scanTask;
    updateAdminProxyScanButton();
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
    state.scanTask = payload.task || state.scanTask;
    if (payload.phase === 'started' && payload.reason === 'manual_proxy_only') state.proxyOnlyScanning = true;
    if (payload.phase === 'completed') state.proxyOnlyScanning = false;
    if (payload.phase === 'started') clearRefreshingTags();
    if (payload.phase === 'completed') setTimeout(clearRefreshingTags, 300);
    if (state.submittedSourceToken && payload.token === state.submittedSourceToken) {
      if (payload.phase === 'source_started') {
        setSourceImportProgress(payload.token, 'Scanning shop products...', 'running');
      } else if (payload.phase === 'source_completed') {
        setSourceImportProgress(payload.token, `Refresh complete: ${Number(payload.matched || 0)} products found.`, 'done');
        if (searchTargetsSource(state.search, payload.token)) void reloadProducts();
      } else if (payload.phase === 'source_error') {
        setSourceImportProgress(payload.token, `Refresh failed: ${payload.error || 'unknown error'}`, 'error');
      }
    }
    setScanning(Boolean(payload.scanning), scanMessage(payload));
  });
  stream.addEventListener('sponsored_update', (event) => {
    const payload = JSON.parse(event.data);
    state.sponsoredUpdate = { ...state.sponsoredUpdate, ...payload };
    updateAdminProxyScanButton();
    if (payload.phase === 'paused') {
      const label = `赞助更新暂停：${payload.current_token || '当前店铺'} ${payload.last_error || ''}`;
      elements.scanDetail.textContent = label;
      toast(label, true);
    } else if (payload.phase === 'source_started') {
      elements.scanDetail.textContent = `赞助更新 ${payload.next_position || payload.position || 0}/${payload.total || 0}：${payload.current_token || ''}`;
    }
  });
  stream.addEventListener('snapshot', (event) => {
    const payload = JSON.parse(event.data);
    const nextRevision = Number(payload.catalog_revision || state.catalogRevision);
    const mappingChanged = nextRevision !== state.catalogRevision;
    state.sources = payload.sources || state.sources;
    state.stats = payload.stats || state.stats;
    state.catalogRevision = nextRevision;
    state.scanTask = payload.scan_task || state.scanTask;
    state.sponsoredUpdate = payload.sponsored_update || state.sponsoredUpdate;
    updateAdminProxyScanButton();
    renderSources();
    updateStats();
    renderTabs();
    if (mappingChanged) void reloadProducts();
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
  stream.addEventListener('priceai_sync', (event) => {
    const payload = JSON.parse(event.data);
    state.priceaiSyncing = payload.phase === 'started';
    if (payload.phase === 'completed') {
      toast(`PriceAI 同步完成：${Number(payload.matched || 0)} 件，更新 ${Number(payload.changed || 0)} 件`);
      void loadState();
    } else if (payload.phase === 'error') {
      toast(`PriceAI 同步失败：${payload.error}`, true);
    }
    updateAdminProxyScanButton();
  });
}

function scanMessage(payload) {
  if (payload.phase === 'waiting_for_user') return '正在等待用户刷新写入完成';
  if (payload.phase === 'source_started') return `正在扫描 ${payload.token}（${payload.source_index}/${payload.source_total}）`;
  if (payload.phase === 'source_completed') return `${payload.name || payload.token}：匹配 ${payload.matched} 件`;
  if (payload.phase === 'source_error') return `${payload.token}：${payload.error}`;
  if (payload.phase === 'completed') return '本轮扫描完成';
  return payload.scanning ? '商品正在逐条刷新' : (state.autoScanEnabled ? '自动扫描已开启' : '自动扫描已关闭');
}

function renderSources() {
  if (!elements.sourceList || !elements.dialog.open) return;
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
    const actions = state.adminVerified
      ? `<div class="source-actions"><button type="button" data-action="toggle">${source.enabled ? '停用' : '启用'}</button><button type="button" class="danger" data-action="delete">删除</button></div>`
      : '';
    return `<div class="source-item" data-token="${escapeHtml(source.token)}">
      <div class="source-name"><strong>${escapeHtml(source.name || source.token)}</strong><span>${escapeHtml(platform)} · ${escapeHtml(source.origin || '手动添加')} · ${source.product_count || 0} 件${escapeHtml(entryText)}${source.last_error ? ` · ${escapeHtml(source.last_error)}` : ''}</span></div>
      <span class="source-status ${escapeHtml(source.status)}">${escapeHtml(statusText)}</span>
      ${actions}
    </div>`;
  }).join('');
}

function historyBucket(timestamp, granularity) {
  const date = new Date(Number(timestamp) * 1000);
  if (granularity === 'hour') return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}`;
  if (granularity === 'day') return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  const monday = new Date(date); const offset = (monday.getDay() + 6) % 7;
  monday.setDate(monday.getDate() - offset); monday.setHours(0, 0, 0, 0);
  return `${monday.getFullYear()}-${monday.getMonth()}-${monday.getDate()}`;
}

function historyTimeLabel(timestamp, granularity) {
  const date = new Date(Number(timestamp) * 1000);
  if (granularity === 'hour') return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:00`;
  if (granularity === 'day') return `${date.getMonth() + 1}/${date.getDate()}`;
  const monday = new Date(date); const offset = (monday.getDay() + 6) % 7;
  monday.setDate(monday.getDate() - offset);
  return `${monday.getMonth() + 1}/${monday.getDate()} 周`;
}

function historySeries(history, mode, granularity) {
  const points = [...history].sort((a, b) => Number(a.recorded_at) - Number(b.recorded_at));
  const usable = mode === 'price'
    ? points.filter((point) => Number.isFinite(Number(point.price)) && Number(point.price) >= 0).map((point) => ({ ...point, value: Number(point.price) }))
    : points.filter((point) => Number.isFinite(Number(point.stock_count)) && Number(point.stock_count) >= 0).map((point) => ({ ...point, value: Number(point.stock_count) }));
  const buckets = new Map();
  for (const point of usable) buckets.set(historyBucket(point.recorded_at, granularity), point);
  return [...buckets.values()];
}

function historySvg(history, mode, granularity) {
  const points = historySeries(history, mode, granularity);
  const labels = { price: '价格', stock: '库存余量' };
  if (!points.length) return `<div class="history-empty">暂无可用${labels[mode]}节点，等待下一次成功刷新。</div>`;

  const width = 760, height = 280;
  const margin = { left: 58, right: 20, top: 20, bottom: 40 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = points.map((point) => Number(point.value));
  let minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * .12, maximum * .03, .5);
  minimum = Math.max(0, minimum - padding);
  maximum += padding;
  const range = Math.max(.01, maximum - minimum);
  const x = (index) => points.length === 1 ? margin.left + chartWidth / 2 : margin.left + index * chartWidth / (points.length - 1);
  const y = (value) => margin.top + (maximum - value) * chartHeight / range;
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(2)} ${y(Number(point.value)).toFixed(2)}`).join(' ');
  const area = `${path} L ${x(points.length - 1).toFixed(2)} ${margin.top + chartHeight} L ${x(0).toFixed(2)} ${margin.top + chartHeight} Z`;
  const grids = Array.from({ length: 5 }, (_, index) => {
    const value = maximum - index * range / 4;
    const lineY = margin.top + index * chartHeight / 4;
    return `<line x1="${margin.left}" y1="${lineY}" x2="${width - margin.right}" y2="${lineY}"/><text x="${margin.left - 9}" y="${lineY + 4}" text-anchor="end">${Math.round(value)}</text>`;
  }).join('');
  const circles = points.map((point, index) => {
    const value = mode === 'price' ? `¥${money(point.value)}` : Math.round(point.value);
    const detail = mode === 'price' ? `库存 ${escapeHtml(point.stock_count)}` : `价格 ¥${money(point.price)}`;
    return `<circle cx="${x(index)}" cy="${y(Number(point.value))}" r="3"><title>${escapeHtml(dateTime(point.recorded_at))} · ${escapeHtml(labels[mode])} ${value} · ${detail}</title></circle>`;
  }).join('');
  const tickIndexes = [...new Set([0, Math.round((points.length - 1) / 2), points.length - 1])];
  const times = tickIndexes.map((index) => `<text class="chart-time" x="${x(index)}" y="${height - 12}" text-anchor="${index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}">${escapeHtml(historyTimeLabel(points[index].recorded_at, granularity))}</text>`).join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(labels[mode])}随刷新时间变化的折线图">
    <g class="chart-grid">${grids}</g><path class="chart-area ${mode === 'price' ? 'chart-price-area' : ''}" d="${area}"/><path class="chart-line ${mode === 'price' ? 'chart-price-line' : ''}" d="${path}"/><g class="chart-points ${mode === 'price' ? 'chart-price-points' : ''}">${circles}</g>
    ${times}
  </svg>`;
}

function renderHistoryChart() {
  for (const button of elements.historyModes.querySelectorAll('[data-history-mode]')) {
    const active = button.dataset.historyMode === state.historyMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  }
  for (const button of elements.historyGranularity.querySelectorAll('[data-history-granularity]')) {
    const active = button.dataset.historyGranularity === state.historyGranularity;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  }
  elements.historyChart.innerHTML = historySvg(state.history, state.historyMode, state.historyGranularity);
}

async function openPriceHistory(goodsKey) {
  const product = state.products.get(goodsKey);
  if (!product) return;
  elements.historyTitle.textContent = product.name;
  elements.historyShop.textContent = product.source_name || product.source_token;
  elements.historyToken.textContent = product.source_token;
  elements.historySummary.innerHTML = '';
  elements.historyChart.innerHTML = '<p>正在加载刷新节点…</p>';
  if (!elements.historyDialog.open) elements.historyDialog.showModal();
  try {
    const payload = await api(`api/history/${encodeURIComponent(goodsKey)}`);
    const history = payload.history || [];
    state.history = history;
    state.historyMode = 'price';
    state.historyGranularity = 'hour';
    const prices = history.map((point) => Number(point.price)).filter(Number.isFinite);
    const latest = history[0] || { price: product.price, recorded_at: product.last_seen };
    const lowest = prices.length ? Math.min(...prices) : Number(product.price);
    const highest = prices.length ? Math.max(...prices) : Number(product.price);
    elements.historySummary.innerHTML = `
      <article><span>最新价</span><strong>¥${money(latest.price)}</strong></article>
      <article><span>最低价</span><strong>¥${money(lowest)}</strong></article>
      <article><span>最高价</span><strong>¥${money(highest)}</strong></article>
      <article><span>刷新节点</span><strong>${history.length}</strong></article>`;
    renderHistoryChart();
  } catch (error) {
    elements.historyChart.innerHTML = `<div class="history-empty">${escapeHtml(error.message)}</div>`;
  }
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

for (const closeButton of document.querySelectorAll('.side-ad-close')) {
  closeButton.addEventListener('click', () => closeButton.closest('.side-ad')?.remove());
}
for (const carousel of document.querySelectorAll('[data-ad-carousel]')) {
  const images = [...carousel.querySelectorAll(':scope > img')];
  const dots = [...carousel.querySelectorAll('.side-ad-dots i')];
  let index = 0; let timer = 0; let startX = 0; let pointerId = null; let suppressPreviewUntil = 0;
  images.forEach((image) => { image.draggable = false; });
  const showSlide = (nextIndex) => {
    index = (nextIndex + images.length) % images.length;
    images.forEach((image, position) => image.classList.toggle('active', position === index));
    dots.forEach((dot, position) => dot.classList.toggle('active', position === index));
  };
  const restartAuto = () => {
    clearInterval(timer);
    if (images.length > 1) timer = setInterval(() => showSlide(index + 1), 4000);
  };
  restartAuto();
  dots.forEach((dot, position) => dot.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    showSlide(position);
    restartAuto();
  }));
  carousel.addEventListener('pointerdown', (event) => {
    if (event.target.closest('.side-ad-dots')) return;
    if (images.length < 2) return;
    pointerId = event.pointerId;
    startX = event.clientX;
    carousel.setPointerCapture(pointerId);
    carousel.classList.add('dragging');
  });
  carousel.addEventListener('pointerup', (event) => {
    if (pointerId !== event.pointerId) return;
    const distance = event.clientX - startX;
    carousel.releasePointerCapture(pointerId);
    carousel.classList.remove('dragging');
    pointerId = null;
    if (Math.abs(distance) >= 32) {
      showSlide(index + (distance < 0 ? 1 : -1));
      suppressPreviewUntil = Date.now() + 350;
      restartAuto();
    }
  });
  carousel.addEventListener('pointercancel', () => {
    pointerId = null;
    carousel.classList.remove('dragging');
  });
  carousel.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key) || images.length < 2) return;
    event.preventDefault();
    showSlide(index + (event.key === 'ArrowRight' ? 1 : -1));
    restartAuto();
  });
  carousel.addEventListener('click', () => {
    if (Date.now() < suppressPreviewUntil) return;
    const active = images.find((image) => image.classList.contains('active')) || images[0];
    if (!active) return;
    const preview = document.querySelector('#adPreviewDialog');
    const previewImage = document.querySelector('#adPreviewImage');
    previewImage.src = active.currentSrc || active.src;
    previewImage.alt = active.alt || '广告宣传大图';
    if (!preview.open) preview.showModal();
  });
}
const adPreviewDialog = document.querySelector('#adPreviewDialog');
document.querySelector('#adPreviewClose')?.addEventListener('click', () => adPreviewDialog.close());
adPreviewDialog?.addEventListener('click', (event) => {
  if (event.target === adPreviewDialog) adPreviewDialog.close();
});

async function joinServerProductRefresh(goodsKey) {
  setProductRefreshing(goodsKey, true);
  toast('服务器正在刷新同店数据，正在接收对应商品更新');
  try {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const payload = await api(`api/products/${encodeURIComponent(goodsKey)}/refresh-status`);
      if (payload.product) applySingleProductRefresh(payload.product);
      if (!payload.refreshing) return;
      await delay(1500);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    setProductRefreshing(goodsKey, false);
  }
}

async function refreshProductOnServer(goodsKey) {
  const headers = getAdminHeaders();
  if (!headers) return false;
  setProductRefreshing(goodsKey, true);
  try {
    const result = await api(`api/products/${encodeURIComponent(goodsKey)}/refresh`, {
      method: 'POST',
      headers,
    });
    state.adminVerified = true;
    if (result.joined) {
      await joinServerProductRefresh(goodsKey);
      return true;
    }
    if (result.product) applySingleProductRefresh(result.product);
    if (result.removed) applySingleProductRemoval(goodsKey);
    toast(result.message || '服务器已刷新该商品');
    return true;
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
    return false;
  } finally {
    setProductRefreshing(goodsKey, false);
    updateAdminProxyScanButton();
  }
}

async function refreshProduct(goodsKey) {
  if (!goodsKey || state.refreshingProducts.has(goodsKey) || state.localScanning) return;
  const product = state.products.get(goodsKey);
  if (!product) return;
  const source = state.sources.find((item) => item.token === product.source_token);
  if (source?.source_kind !== 'shop_api') {
    toast('该商品由 PriceAI 快照维护，请使用同步 PriceAI 更新', true);
    return;
  }
  if (state.adminVerified) {
    await refreshProductOnServer(goodsKey);
    return;
  }
  try {
    const status = await api(`api/products/${encodeURIComponent(goodsKey)}/refresh-status`);
    if (status.refreshing) {
      await joinServerProductRefresh(goodsKey);
      return;
    }
  } catch (error) {
    toast(error.message, true);
    return;
  }
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

async function refreshProductWithLocalIp(goodsKey) {
  if (!goodsKey || state.refreshingProducts.has(goodsKey) || state.localScanning) return;
  const product = state.products.get(goodsKey);
  if (product?.off_shelf) {
    toast('已下架商品不会再刷新', true);
    return;
  }
  const visitorLazyProduct = product && (Boolean(product.platform_banned)
    || (Number(product.stock_count) === 0 && Number(product.out_of_stock_since || 0) > 0
      && Date.now() / 1000 - Number(product.out_of_stock_since) >= 24 * 60 * 60));
  if (visitorLazyProduct && !state.adminVerified) {
    toast('长期缺货商品每日极懒更新；平台封禁商品由服务器后台复查', true);
    return;
  }
  const configuredSource = state.sources.find((item) => item.token === product?.source_token);
  const source = configuredSource || fallbackLocalSource(product);
  if (product?.source_token === 'priceai.cc:top5' || source?.source_kind === 'snapshot') {
    try {
      const result = await api(`api/products/${encodeURIComponent(goodsKey)}/priceai-refresh`, {
        method: 'POST',
      });
      toast(result.started ? 'PriceAI snapshot refresh started.' : 'PriceAI snapshot refresh is already running.');
    } catch (error) {
      toast(`PriceAI refresh failed: ${error.message}`, true);
    }
    return;
  }
  if (!product || !source || source.source_kind !== 'shop_api') {
    toast('This product cannot be refreshed from a local shop API.', true);
    return;
  }

  setProductRefreshing(goodsKey, true);
  setLocalScanning(true, `Refreshing ${product.name} through this device`, '1 / 1', 'filter');
  try {
    const item = await localMarketplacePost(
      sourceBaseUrl(source),
      '/shopApi/Shop/goodsInfo',
      { goods_key: product.goods_key },
    );
    if (!item?.goods_key) throw new Error('The shop API did not return this product.');
    const result = await api('api/local-scan/products', {
      method: 'POST',
      body: JSON.stringify({
        token: source.token,
        source_name: product.source_name || source.name || source.token,
        items: [compactLocalItem(item, item.goods_type || product.goods_type || '')],
        requested_keys: [product.goods_key],
      }),
    });
    await refreshVisibleProducts([product.goods_key], state.productRequestId);
    toast(result.changed ? 'Product refreshed through this device.' : 'Product information is already current.');
  } catch (error) {
    if (isLocalOffShelfError(error)) {
      try {
        await markLocalProductOffShelf(product, source, error.message);
        await refreshVisibleProducts([product.goods_key], state.productRequestId);
        toast('商品未上架，已移入“已下架”');
      } catch (reportError) {
        toast(`商品未上架，但更新服务器状态失败: ${reportError.message}`, true);
      }
    } else {
      toast(`Local refresh failed: ${error.message}`, true);
    }
  } finally {
    setProductRefreshing(goodsKey, false);
    setLocalScanning(false, state.autoScanEnabled ? 'Automatic scanning is enabled.' : 'Automatic scanning is paused.', '', 'filter');
  }
}

function isLocalOffShelfError(error) {
  const message = String(error?.message || error || '').toLowerCase();
  return ['商品未上架', '商品已下架', '商品不存在', '不存在或已下架',
    'goods not found', 'item not found', 'not listed', 'off shelf', 'off-shelf']
    .some((marker) => message.includes(marker));
}

async function markLocalProductOffShelf(product, source, reason = '') {
  return api('api/local-scan/products', {
    method: 'POST',
    body: JSON.stringify({
      token: source.token,
      source_name: product.source_name || source.name || source.token,
      items: [],
      requested_keys: [product.goods_key],
      off_shelf_reason: String(reason).slice(0, 300),
    }),
  });
}

const LOCAL_LDXP_BASE_URL = 'https://pay.ldxp.cn';
const LOCAL_GOODS_TYPES = ['card', 'article', 'resource', 'equity'];
const LOCAL_PAGE_SIZE = 300;
const LOCAL_MAX_PAGES = 20;

function fallbackLocalSource(product) {
  const token = String(product?.source_token || '');
  if (!token || token.startsWith('priceai.')) return null;
  if (token.startsWith('catfk.com:')) {
    return {
      token,
      source_kind: 'shop_api',
      base_url: 'https://catfk.com',
      remote_token: token.slice('catfk.com:'.length),
      name: product.source_name || token,
    };
  }
  return {
    token,
    source_kind: 'shop_api',
    base_url: LOCAL_LDXP_BASE_URL,
    remote_token: token,
    name: product.source_name || token,
  };
}

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
  if (source?.source_kind !== 'shop_api') {
    throw new Error('该来源不是可本地扫描的店铺 API');
  }
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
  if (source.validation_required || ['error', 'paused', 'pending'].includes(source.status)) {
    for (const [goodsKey, listing] of items) {
      const detail = await localMarketplacePost(baseUrl, '/shopApi/Shop/goodsInfo', { goods_key: goodsKey });
      const compact = compactLocalItem({
        ...listing,
        ...detail,
        category: detail?.category || listing.category,
        goods_type: detail?.goods_type || listing.goods_type,
      }, detail?.goods_type || listing.goods_type || '');
      items.set(goodsKey, compact);
    }
  }
  return {
    sourceName: String(shop?.nickname || source.name || source.token).slice(0, 200),
    items: [...items.values()],
  };
}

async function collectSourceWithLocalHelper(source) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10 * 60_000);
  try {
    const response = await fetch('http://127.0.0.1:18766/scan-source', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source }),
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || `本地助手返回 HTTP ${response.status}`);
    return { sourceName: payload.source_name || source.name || source.token, items: payload.items || [] };
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('本地采集助手扫描超时');
    if (error instanceof TypeError) throw new Error('未检测到本地网页采集助手，请先运行“本地网页采集助手.bat”');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function scheduleVisibleProductValidation(goodsKeys = []) {
  for (const key of goodsKeys) {
    const card = findProductCard(key);
    if (card && !card.dataset.displayedAt) card.dataset.displayedAt = String(Date.now());
  }
  clearTimeout(state.localValidationTimer);
  const pending = [...elements.grid.children]
    .filter((card) => !state.locallyValidatedProducts.has(card.dataset.key));
  if (!pending.length) return;
  const earliest = Math.min(...pending.map((card) => Number(card.dataset.displayedAt || Date.now()) + 10_000));
  state.localValidationTimer = setTimeout(() => { void validateVisibleProductsLocally(); }, Math.max(0, earliest - Date.now()));
}

async function refillValidatedProducts(targetCount) {
  if (elements.grid.children.length >= targetCount) return;
  const requestId = state.productRequestId;
  const query = currentProductQuery(Math.min(500, targetCount), 0);
  await readProductStream(query, (record) => applyProductStreamRecord(record, requestId, 0));
  if (state.streamRenderQueued) flushStreamedProducts();
}

async function validateVisibleProductsLocally() {
  if (state.localValidationRunning || state.localScanning) {
    scheduleVisibleProductValidation();
    return;
  }
  const now = Date.now();
  const products = [...elements.grid.children]
    .filter((card) => now - Number(card.dataset.displayedAt || now) >= 10_000)
    .map((card) => state.products.get(card.dataset.key))
    .filter((product) => product && !product.off_shelf && !product.platform_banned
      && !state.locallyValidatedProducts.has(product.goods_key))
    .slice(0, 12);
  if (!products.length) {
    scheduleVisibleProductValidation();
    return;
  }
  state.localValidationRunning = true;
  products.forEach((product) => state.locallyValidatedProducts.add(product.goods_key));
  try {
    const response = await fetch('http://127.0.0.1:18766/verify-products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        products: products.map(({ goods_key, link }) => ({ goods_key, link })),
      }),
    });
    const local = await response.json();
    if (!response.ok || !local.ok) throw new Error(local.error || '本地商品核验失败');
    const summary = await api('api/local-validation/products', {
      method: 'POST', body: JSON.stringify({ results: local.results || [] }),
    });
    const unavailableKeys = summary.unavailable_keys || [];
    if (unavailableKeys.length) {
      const targetCount = elements.grid.children.length;
      unavailableKeys.forEach((key) => applySingleProductRemoval(key));
      await refillValidatedProducts(targetCount);
    }
    if (Number(summary.changed || 0) > 0) await loadState();
  } catch (error) {
    if (!(error instanceof TypeError)) console.warn('Visible product validation failed:', error);
  } finally {
    state.localValidationRunning = false;
    scheduleVisibleProductValidation();
  }
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

async function localFilteredScan(scopeLabel = '当前筛选') {
  if (state.localScanning) return;
  if (state.adminVerified) {
    await startServerFullScan();
    return;
  }
  setLocalScanning(true, `正在向服务器领取${scopeLabel}刷新任务`, '领取刷新任务', 'filter');
  try {
    const allocation = await api('api/user-refresh/claim', {
      method: 'POST', body: JSON.stringify(currentUserRefreshScope()),
    });
    const products = allocation.products || [];
    if (!products.length) {
      toast(`${scopeLabel}没有可刷新的商品`, true);
      return;
    }
    setLocalScanning(true, `已领取服务器队列 ${allocation.offset + 1}-${allocation.next_offset} / ${allocation.total}，开始逐个刷新`, `筛选刷新 0/${products.length}`, 'filter');
    const result = await refreshLocalProducts(products, (source, current, total) => {
      setLocalScanning(
        true,
        `正在用当前设备刷新 ${source.sourceName}`,
        `筛选刷新 ${current}/${total}`,
        'filter',
      );
    });
    toast(`${scopeLabel}刷新完成：提交 ${result.requested} 件，匹配 ${result.matched} 件，失败 ${result.failed} 组`, result.failed > 0);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已在后台开启' : '服务器自动扫描已在后台暂停', '', 'filter');
    await loadState();
  }
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitForServerRefreshBatch() {
  while (true) {
    const status = await api('api/category-refresh/server-status');
    elements.browserFactoryStatus.textContent = `服务器刷新 ${status.completed || 0}/${status.total || 0}`;
    if (!status.running) return status;
    await wait(800);
  }
}

async function runAlternatingCategoryRefresh(availability, scopeLabel) {
  if (state.localScanning) return;
  const category = state.selectedCategory;
  const cycleId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const payload = { category, availability, limit: 50, cycle_id: cycleId };
  let processed = 0;
  let targetTotal = null;
  let failed = 0;
  setLocalScanning(true, `准备刷新${scopeLabel}`, '准备任务', 'filter');
  elements.browserFactoryStatus.classList.remove('success', 'error');
  try {
    while (targetTotal === null || processed < targetTotal) {
      const clientBatch = await api('api/user-refresh/claim', {
        method: 'POST', body: JSON.stringify(payload),
      });
      if (targetTotal === null) targetTotal = Number(clientBatch.total || 0);
      const clientProducts = (clientBatch.products || []).slice(0, Math.max(0, targetTotal - processed));
      if (!clientProducts.length) break;
      elements.browserFactoryStatus.textContent = `本机刷新 ${processed}/${targetTotal}`;
      const local = await refreshLocalProducts(clientProducts, (_source, current, total) => {
        elements.browserFactoryStatus.textContent = `本机刷新 ${processed + current}/${targetTotal} · 店铺 ${current}/${total}`;
      });
      processed += clientProducts.length;
      failed += Number(local.failed || 0);
      if (processed >= targetTotal) break;

      const serverLimit = Math.min(50, targetTotal - processed);
      const server = await api('api/category-refresh/server', {
        method: 'POST', body: JSON.stringify({ ...payload, limit: serverLimit }),
      });
      if (!server.started) {
        await waitForServerRefreshBatch();
        continue;
      }
      const serverResult = await waitForServerRefreshBatch();
      processed += Number(serverResult.total || serverLimit);
      failed += Number(serverResult.failed || 0);
    }
    elements.browserFactoryStatus.textContent = `${scopeLabel}完成 ${Math.min(processed, targetTotal || 0)}/${targetTotal || 0}`;
    elements.browserFactoryStatus.classList.add(failed ? 'error' : 'success');
    toast(`${scopeLabel}刷新完成：${Math.min(processed, targetTotal || 0)} 件，失败 ${failed} 件`, failed > 0);
  } catch (error) {
    elements.browserFactoryStatus.textContent = `${scopeLabel}中断：${error.message}`;
    elements.browserFactoryStatus.classList.add('error');
    toast(error.message, true);
  } finally {
    setLocalScanning(false, '', '', 'filter');
    await loadState();
  }
}

function refreshCurrentCategory() {
  const stockOnly = ['plus_sms', 'k12'].includes(state.selectedCategory);
  const availability = stockOnly ? 'stock' : 'all';
  const label = stockOnly ? '当前分类有货商品' : '当前分类全部在售商品';
  return runAlternatingCategoryRefresh(availability, label);
}

async function runBrowserFactory(errorSourcesOnly = false) {
  if (state.localScanning) return;
  elements.browserFactoryStatus.textContent = '正在领取任务...';
  elements.browserFactoryStatus.classList.remove('success', 'error');
  setLocalScanning(true, '正在领取服务器刷新任务', '工厂任务准备中', 'filter');
  try {
    const multiplier = errorSourcesOnly ? 1 : Math.max(1, Math.min(5, Math.trunc(Number(elements.browserFactoryMultiplier.value) || 1)));
    if (!errorSourcesOnly) elements.browserFactoryMultiplier.value = String(multiplier);
    const allocation = await api(errorSourcesOnly ? 'api/browser-factory/claim-errors' : 'api/browser-factory/claim', {
      method: 'POST', body: JSON.stringify({ multiplier }),
    });
    const sources = allocation.sources || [];
    if (!sources.length) {
      const emptyMessage = errorSourcesOnly ? '当前没有可重试的异常采集源' : '当前没有可领取的服务器刷新任务';
      toast(emptyMessage);
      elements.browserFactoryStatus.textContent = emptyMessage;
      return;
    }
    let completed = 0; let failed = 0; let matched = 0;
    elements.browserFactoryStatus.textContent = `已领取 ${sources.length} 个 · 0/${sources.length}`;
    for (let index = 0; index < sources.length; index += 1) {
      const source = sources[index];
      elements.browserFactoryStatus.textContent = `${index + 1}/${sources.length} · 成功 ${completed} · 失败 ${failed} · ${source.name || source.token}`;
      setLocalScanning(true, `正在刷新 ${source.name || source.token}`, `工厂任务 ${index + 1}/${sources.length}`, 'filter');
      try {
        const collected = errorSourcesOnly
          ? await collectSourceWithLocalHelper(source)
          : await collectLocalSource(source);
        const result = await api('api/local-scan/source', {
          method: 'POST',
          body: JSON.stringify({
            token: source.token,
            source_name: collected.sourceName,
            items: collected.items,
            complete: true,
            lease_id: allocation.lease_id,
          }),
        });
        completed += 1;
        matched += Number(result.matched || 0);
        elements.browserFactoryStatus.textContent = `${index + 1}/${sources.length} · 成功 ${completed} · 失败 ${failed} · 匹配 ${matched}`;
      } catch (error) {
        failed += 1;
        const reason = String(error.message || error).slice(0, 80);
        elements.browserFactoryStatus.textContent = `${index + 1}/${sources.length} · 成功 ${completed} · 失败 ${failed} · ${reason}`;
        try {
          await api('api/browser-factory/release', {
            method: 'POST', body: JSON.stringify({ token: source.token, lease_id: allocation.lease_id }),
          });
        } catch (releaseError) {
          console.warn(`Browser factory lease release failed for ${source.token}:`, releaseError);
        }
        console.warn(`Browser factory task failed for ${source.token}:`, error);
      }
    }
    elements.browserFactoryStatus.textContent = `完成 ${sources.length}/${sources.length} · 成功 ${completed} · 失败 ${failed} · 匹配 ${matched}`;
    elements.browserFactoryStatus.classList.add(failed > 0 ? 'error' : 'success');
    toast(`工厂任务完成：成功 ${completed}，失败 ${failed}，匹配 ${matched} 件`, failed > 0);
  } catch (error) {
    elements.browserFactoryStatus.textContent = `领取失败：${error.message}`;
    elements.browserFactoryStatus.classList.add('error');
    toast(error.message, true);
  } finally {
    setLocalScanning(false, state.autoScanEnabled ? '服务器自动扫描已开启' : '服务器自动扫描已暂停', '', 'filter');
    await loadState();
  }
}

async function loadAllFilteredProducts(onProgress) {
  const products = [];
  let offset = 0;
  let total = 0;
  while (true) {
    let nextOffset = offset;
    await readProductStream(currentProductQuery(500, offset), (record) => {
      if (record.type === 'meta') {
        total = Number(record.total || 0);
        nextOffset = Number(record.next_offset || offset);
      } else if (record.type === 'product' && record.product) {
        products.push(record.product);
        onProgress?.(products.length, total);
      }
    });
    if (!total || nextOffset >= total || nextOffset <= offset) break;
    offset = nextOffset;
  }
  return products;
}

async function localManualScan() {
  if (state.localScanning) return;
  if (!state.adminVerified) {
    toast('全量更新已改由服务器队列执行，请使用管理员令牌启动服务器全量扫描', true);
    return;
  }
  await startServerFullScan();
  return;
  /* Legacy local full-store scan kept below for reference; normal users no longer run it. */
  const allSources = state.sources.filter(
    (source) => source.enabled && source.source_kind === 'shop_api'
  );
  const sources = allSources.slice(0, REGULAR_USER_REFRESH_LIMIT);
  if (!sources.length) {
    toast('没有已启用的采集源', true);
    return;
  }

  let succeeded = 0;
  let failed = 0;
  let matched = 0;
  if (allSources.length > sources.length) toast(`普通用户每次最多刷新 ${REGULAR_USER_REFRESH_LIMIT} 个店铺，本次仅扫描前 ${sources.length} 个`);
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
  if (!elements.dialog.open) elements.dialog.showModal();
  renderSources();
}

function applyPriceRange() {
  const minimum = Number(elements.priceMin.value || 0);
  const maximumText = elements.priceMax.value.trim();
  const maximum = maximumText === '' ? null : Number(maximumText);
  if (!Number.isFinite(minimum) || minimum < 0 || (maximum !== null && (!Number.isFinite(maximum) || maximum < 0))) {
    toast('价格范围必须是非负数字', true);
    return;
  }
  if (maximum !== null && maximum < minimum) {
    toast('最高价格不能低于最低价格', true);
    return;
  }
  state.minPrice = minimum;
  state.maxPrice = maximum;
  state.includeMinPrice = elements.includeMinPrice.checked;
  renderProducts();
}

function commentSort(a, b) {
  return Number(b.pinned) - Number(a.pinned)
    || Number(b.pinned_at) - Number(a.pinned_at)
    || Number(b.created_at) - Number(a.created_at);
}

function compressCommentImage(file) {
  return new Promise((resolve, reject) => {
    const image = new Image(); const source = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(source); const scale = Math.min(1, 1600 / Math.max(image.width, image.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale));
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => { if (!blob) { reject(new Error('图片转换失败')); return; } const reader = new FileReader(); reader.onload = () => resolve({ data: reader.result, preview: URL.createObjectURL(blob) }); reader.onerror = () => reject(new Error('图片读取失败')); reader.readAsDataURL(blob); }, 'image/jpeg', .78);
    }; image.onerror = () => { URL.revokeObjectURL(source); reject(new Error('无法读取图片')); }; image.src = source;
  });
}

function renderDrawerImages(target, images) {
  target.innerHTML = images.map((item, index) => `<span><img src="${escapeHtml(item.preview)}" alt="待上传图片"><button type="button" data-remove-comment-image="${index}">×</button></span>`).join('');
}

function addDrawerImages(files, bucket, target) {
  (async () => {
    for (const file of files) {
      if (bucket.length >= 5) { toast('一条评论最多 5 张图片', true); break; }
      if (!/^image\/(png|jpeg)$/.test(file.type)) { toast('只支持 PNG 或 JPEG 图片', true); continue; }
      try { const item = await compressCommentImage(file); if (String(item.data).length > 1_200_000) { URL.revokeObjectURL(item.preview); toast('图片压缩后仍过大', true); } else bucket.push(item); }
      catch (error) { toast(error.message, true); }
    }
    renderDrawerImages(target, bucket);
  })();
}

function scoreButtons() {
  for (const field of document.querySelectorAll('.score-fields > div')) {
    const stars = field.querySelector('.stars');
    if (!stars.children.length) stars.innerHTML = [1, 2, 3, 4, 5].map((value) => `<button type="button" data-score="${value}">★</button>`).join('');
  }
}

function renderDrawerComments() {
  const comments = [...state.commentDrawer.comments.values()].sort(commentSort);
  elements.drawerCommentList.innerHTML = comments.length ? comments.map((comment) => {
    const avatar = comment.avatar ? `<img class="comment-avatar" src="${escapeHtml(comment.avatar)}" alt="">` : `<span class="comment-avatar default-avatar">${escapeHtml((comment.author || '匿').slice(0, 1))}</span>`;
    const ratings = [['商品', comment.product_score], ['商铺', comment.shop_score], ['体验', comment.experience_score]].filter(([, score]) => score !== null && score !== undefined).map(([name, score]) => `<span class="tag">${name} ${Number(score).toFixed(1)} ★</span>`).join('');
    const images = (comment.images || []).map((url) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(url)}" alt="评论图片" loading="lazy"></a>`).join('');
    const pin = comment.pinned ? '<span class="comment-pin">置顶</span>' : '';
    const adminBadge = comment.is_admin ? '<span class="comment-admin-badge">管理员认证</span>' : comment.admin_verified ? '<span class="comment-verified-badge">管理员已认证</span>' : '';
    const pinButton = state.adminVerified ? `<button class="comment-pin-toggle" data-comment-pin="${escapeHtml(comment.id)}" data-pinned="${comment.pinned}">${comment.pinned ? '取消置顶' : '置顶'}</button>` : '';
    const verifyButton = state.adminVerified ? `<button class="comment-pin-toggle" data-comment-verify="${escapeHtml(comment.id)}" data-verified="${comment.admin_verified}">${comment.admin_verified ? '取消认证' : '认证评论'}</button>` : '';
    const replies = (comment.replies || []).map((reply) => `<div class="comment-reply"><strong>${escapeHtml(reply.author || '匿名用户')}${reply.is_admin ? ' · 管理员认证' : ''}</strong><span>${escapeHtml(reply.body)}</span></div>`).join('');
    return `<article class="comment-item ${comment.pinned ? 'pinned' : ''}"><div class="comment-author">${avatar}<strong>${escapeHtml(comment.author || '匿名用户')}</strong>${adminBadge}${pin}<time>${relativeTime(comment.created_at)}</time>${pinButton}${verifyButton}</div>${comment.body ? `<p>${escapeHtml(comment.body)}</p>` : ''}${ratings ? `<div class="tags">${ratings}</div>` : ''}${images ? `<div class="comment-images">${images}</div>` : ''}<div class="comment-replies">${replies}</div><form class="reply-form" data-reply-comment="${escapeHtml(comment.id)}"><textarea maxlength="200" placeholder="回复这条评论…"></textarea><div><button type="button" data-emoji="😀">😀</button><button type="button" data-emoji="👍">👍</button><button type="button" data-emoji="❤️">❤️</button><button type="submit">回复</button></div></form></article>`;
  }).join('') : '<div class="comment-empty">暂无评论，等待第一条分享。</div>';
  const metric = state.commentMetrics.get(state.commentDrawer.goodsKey) || {};
  elements.commentMetric.textContent = metric.rating_count ? `评论 ${metric.comment_count || comments.length} 条 · 加权评分 ${Number(metric.weighted_score).toFixed(2)} · ${metric.rating_count} 项评分` : `评论 ${metric.comment_count || comments.length} 条 · 暂无参与评分`;
}

async function fetchDrawerComments(after = 0) {
  const key = state.commentDrawer.goodsKey; if (!key) return;
  const payload = await api(`api/products/${encodeURIComponent(key)}/comments?after=${after}`);
  for (const comment of payload.comments || []) state.commentDrawer.comments.set(comment.id, comment);
  state.commentMetrics.set(key, payload.metrics || {}); renderDrawerComments();
}

async function openCommentDrawer(goodsKey, push = true) {
  const product = state.products.get(goodsKey); if (!product) return;
  state.commentDrawer.goodsKey = goodsKey;
  if (!state.commentDrawer.comments.size || state.commentDrawer.lastKey !== goodsKey) { state.commentDrawer.comments = new Map(); state.commentDrawer.lastKey = goodsKey; }
  elements.commentDialogTitle.textContent = product.name;
  elements.commentDialogProduct.innerHTML = `${product.image ? `<img src="${escapeHtml(product.image)}" alt="" referrerpolicy="no-referrer">` : '<span class="fallback">LDXP</span>'}<div><small>${escapeHtml(product.source_name || product.source_token)}</small><strong>${escapeHtml(product.name)}</strong></div>`;
  scoreButtons(); if (!elements.commentDialog.open) elements.commentDialog.showModal();
  if (push) history.pushState({ ldxpCommentGoodsKey: goodsKey }, '', `#comments=${encodeURIComponent(goodsKey)}`);
  try { await fetchDrawerComments(); } catch (error) { toast(error.message, true); }
}

function closeCommentDrawer(fromHistory = false) {
  if (!elements.commentDialog.open) return;
  elements.commentDialog.close();
  if (!fromHistory && history.state?.ldxpCommentGoodsKey) history.back();
}

function submitDrawerComment(body, images, scores = {}) {
  const key = state.commentDrawer.goodsKey; if (!key) return Promise.reject(new Error('未选择商品'));
  const headers = state.adminVerified ? getAdminHeaders() : {};
  return api(`api/products/${encodeURIComponent(key)}/comments`, { method: 'POST', headers: headers || {}, body: JSON.stringify({ author: elements.drawerCommentAuthor.value.trim(), avatar: state.commentDrawer.avatar?.data || '', body, images: images.map((item) => item.data), scores }) }).then((payload) => {
    state.commentDrawer.comments.set(payload.comment.id, payload.comment);
    const previews = state.commentPreviews.get(key) || []; state.commentPreviews.set(key, [payload.comment, ...previews.filter((item) => item.id !== payload.comment.id)].slice(0, 10));
    state.commentMetrics.set(key, payload.metrics || state.commentMetrics.get(key) || {}); updateCommentPreview(key); renderDrawerComments(); return payload;
  });
}

document.addEventListener('click', (event) => {
  const voteButton = event.target.closest('[data-comment-vote]');
  if (voteButton) {
    event.preventDefault(); event.stopPropagation();
    const card = voteButton.closest('.product-card'); const goodsKey = card?.dataset.key;
    if (goodsKey) void api(`api/products/${encodeURIComponent(goodsKey)}/comments/${encodeURIComponent(voteButton.dataset.commentId)}/vote`, { method: 'POST', body: JSON.stringify({ voter_key: commentVoterKey, value: Number(voteButton.dataset.commentVote) }) }).then((payload) => { const comments = state.commentPreviews.get(goodsKey) || []; const target = comments.find((comment) => comment.id === payload.vote.id); if (target) { target.upvotes = payload.vote.upvotes; target.downvotes = payload.vote.downvotes; updateCommentPreview(goodsKey); } }).catch((error) => toast(error.message, true));
    return;
  }
  const commentArea = event.target.closest('.comment-area-button');
  if (commentArea) { event.preventDefault(); event.stopPropagation(); const goodsKey = commentArea.closest('.product-card')?.dataset.key; if (goodsKey) location.href = `comments.html?product=${encodeURIComponent(goodsKey)}`; return; }
  const commentRefresh = event.target.closest('.comment-refresh-button');
  if (commentRefresh) { event.preventDefault(); event.stopPropagation(); const goodsKey = commentRefresh.closest('.product-card')?.dataset.key; if (goodsKey) void loadCommentPreviews([goodsKey]); return; }
  const commentPreview = event.target.closest('.comment-carousel');
  if (commentPreview) {
    event.preventDefault();
    event.stopPropagation();
    const goodsKey = commentPreview.closest('.product-card')?.dataset.key;
    if (goodsKey) void openCommentDrawer(goodsKey);
    return;
  }
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
    refreshProductWithLocalIp(refreshButton.closest('.product-card')?.dataset.key);
    return;
  }
  const tab = event.target.closest('[data-category]');
  const refreshCategory = event.target.closest('[data-refresh-category]');
  if (refreshCategory) {
    const category = refreshCategory.dataset.refreshCategory;
    const label = category === 'all'
      ? '全部商品'
      : state.categories.find((item) => item.key === category)?.label || category;
    state.selectedCategory = category;
    renderTabs();
    renderProducts();
    void refreshCurrentCategory();
    return;
  }
  if (tab) {
    state.selectedCategory = tab.dataset.category;
    renderTabs(); renderProducts();
  }
});

$('#searchInput').addEventListener('input', (event) => {
  state.search = event.target.value;
  if (isMarketplaceLinkSearch(state.search) && state.stockOnly) {
    state.stockOnly = false;
    $('#stockOnly').checked = false;
  }
  clearTimeout(searchReloadTimer);
  searchReloadTimer = setTimeout(() => renderProducts(), 220);
});
$('#stockOnly').addEventListener('change', (event) => { state.stockOnly = event.target.checked; renderProducts(); });
elements.priceMin.addEventListener('change', applyPriceRange);
elements.priceMax.addEventListener('change', applyPriceRange);
elements.includeMinPrice.addEventListener('change', applyPriceRange);
$('#sortSelect').addEventListener('change', (event) => {
  state.sort = event.target.value;
  if (state.completedFilterKey === currentFilterMappingKey()) {
    sortCompletedFilterMapping();
  } else {
    renderProducts();
  }
});
elements.loadBatchSize.addEventListener('change', (event) => {
  state.productLoadLimit = Number(event.target.value) || 12;
});
elements.loadMoreButton.addEventListener('click', () => { void loadProductBatch(); });
elements.localScanButton.addEventListener('click', localManualScan);
elements.adminTokenVerifyButton.addEventListener('click', () => { void verifyAdminToken(); });
elements.adminTokenInput.addEventListener('input', () => {
  state.adminVerified = false;
  updateAdminProxyScanButton();
  renderSources();
});
elements.adminFullScanButton.addEventListener('click', () => { void startServerFullScan(); });
elements.sponsoredUpdateButton.addEventListener('click', () => { void startSponsoredUpdate(); });
elements.browserFactoryButton.addEventListener('click', () => { void runBrowserFactory(); });
elements.refreshOutOfStockButton.addEventListener('click', () => {
  void runAlternatingCategoryRefresh('out_of_stock', '当前分类缺货商品');
});
elements.refreshOffShelfButton.addEventListener('click', () => {
  void runAlternatingCategoryRefresh('off_shelf', '当前分类下架商品');
});
elements.retryErrorSourcesButton.addEventListener('click', () => { void runBrowserFactory(true); });
elements.adminProxyScanButton.addEventListener('click', () => { void startAdminProxyScan(); });
elements.priceaiSyncButton.addEventListener('click', () => { void startPriceaiSync(); });
elements.historyModes.addEventListener('click', (event) => {
  const button = event.target.closest('[data-history-mode]');
  if (!button) return;
  state.historyMode = button.dataset.historyMode;
  renderHistoryChart();
});
elements.historyGranularity.addEventListener('click', (event) => {
  const button = event.target.closest('[data-history-granularity]');
  if (!button) return;
  state.historyGranularity = button.dataset.historyGranularity;
  renderHistoryChart();
});
elements.ratingSort.addEventListener('change', (event) => { state.ratingSort = event.target.checked; renderProducts(); });
elements.drawerAdminToken.value = sessionStorage.getItem('ldxp-admin-key') || '';
elements.drawerAdminToken.addEventListener('input', () => { elements.adminTokenInput.value = elements.drawerAdminToken.value; state.adminVerified = false; elements.drawerAdminState.textContent = '普通评论'; });
elements.drawerAdminVerify.addEventListener('click', async () => { const key = elements.drawerAdminToken.value.trim(); if (!key) { toast('请输入管理员 Token', true); return; } elements.adminTokenInput.value = key; try { await api('api/admin/verify', { method: 'POST', headers: { 'X-LDXP-Admin-Key': key } }); sessionStorage.setItem('ldxp-admin-key', key); state.adminVerified = true; elements.drawerAdminState.textContent = '管理员认证：发布将标记为管理员评论'; renderDrawerComments(); toast('管理员认证成功'); } catch (error) { state.adminVerified = false; elements.drawerAdminState.textContent = '普通评论'; toast(error.message, true); } });
elements.commentCloseButton.addEventListener('click', () => closeCommentDrawer());
elements.commentRefreshButton.addEventListener('click', () => { const newest = Math.max(0, ...[...state.commentDrawer.comments.values()].map((comment) => Number(comment.created_at) || 0)); void fetchDrawerComments(newest).catch((error) => toast(error.message, true)); });
elements.drawerCommentImages.addEventListener('change', (event) => { addDrawerImages([...event.target.files], state.commentDrawer.images, elements.drawerImagePreview); event.target.value = ''; });
elements.drawerCommentAvatar.addEventListener('change', async (event) => { const file = event.target.files?.[0]; event.target.value = ''; if (!file) return; if (!/^image\/(png|jpeg)$/.test(file.type)) { toast('头像只支持 PNG 或 JPEG 图片', true); return; } try { const avatar = await new Promise((resolve, reject) => { const image = new Image(); const source = URL.createObjectURL(file); image.onload = () => { URL.revokeObjectURL(source); const scale = Math.min(1, 96 / Math.max(image.width, image.height)); const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale)); canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height); canvas.toBlob((blob) => { if (!blob) { reject(new Error('头像转换失败')); return; } const reader = new FileReader(); reader.onload = () => resolve({ data: reader.result, preview: URL.createObjectURL(blob) }); reader.readAsDataURL(blob); }, 'image/jpeg', .76); }; image.onerror = () => { URL.revokeObjectURL(source); reject(new Error('无法读取头像')); }; image.src = source; }); if (String(avatar.data).length > 140000) { URL.revokeObjectURL(avatar.preview); throw new Error('头像压缩后仍过大'); } if (state.commentDrawer.avatar?.preview) URL.revokeObjectURL(state.commentDrawer.avatar.preview); state.commentDrawer.avatar = avatar; elements.drawerAvatarPreview.innerHTML = `<img src="${escapeHtml(avatar.preview)}" alt="待上传头像">`; } catch (error) { toast(error.message, true); } });
elements.quickCommentImages.addEventListener('change', (event) => { addDrawerImages([...event.target.files], state.commentDrawer.quickImages, elements.quickImagePreview); event.target.value = ''; });
elements.drawerImagePreview.addEventListener('click', (event) => { const button = event.target.closest('[data-remove-comment-image]'); if (!button) return; const [item] = state.commentDrawer.images.splice(Number(button.dataset.removeCommentImage), 1); if (item) URL.revokeObjectURL(item.preview); renderDrawerImages(elements.drawerImagePreview, state.commentDrawer.images); });
elements.quickImagePreview.addEventListener('click', (event) => { const button = event.target.closest('[data-remove-comment-image]'); if (!button) return; const [item] = state.commentDrawer.quickImages.splice(Number(button.dataset.removeCommentImage), 1); if (item) URL.revokeObjectURL(item.preview); renderDrawerImages(elements.quickImagePreview, state.commentDrawer.quickImages); });
elements.drawerCommentBody.addEventListener('paste', (event) => { const files = [...(event.clipboardData?.files || [])]; if (files.length) { event.preventDefault(); addDrawerImages(files, state.commentDrawer.images, elements.drawerImagePreview); } });
elements.quickCommentBody.addEventListener('paste', (event) => { const files = [...(event.clipboardData?.files || [])]; if (files.length) { event.preventDefault(); addDrawerImages(files, state.commentDrawer.quickImages, elements.quickImagePreview); } });
document.querySelector('.score-fields').addEventListener('click', (event) => { const button = event.target.closest('[data-score]'); if (!button) return; const field = button.closest('[data-score-field]'); field.dataset.score = button.dataset.score; field.querySelectorAll('[data-score]').forEach((star) => star.classList.toggle('active', Number(star.dataset.score) <= Number(button.dataset.score))); });
elements.drawerCommentForm.addEventListener('click', (event) => { const emoji = event.target.closest('[data-emoji]'); if (!emoji) return; elements.drawerCommentBody.value += emoji.dataset.emoji; elements.drawerCommentBody.focus(); });
elements.drawerCommentForm.addEventListener('submit', async (event) => { event.preventDefault(); const scores = {}; document.querySelectorAll('.score-fields > div').forEach((field) => { if (field.querySelector('input').checked) scores[field.dataset.scoreField] = Number(field.dataset.score || 0); }); const body = elements.drawerCommentBody.value.trim(); if (!body && !state.commentDrawer.images.length && !Object.keys(scores).length) { toast('请填写评论、添加图片或参与评分', true); return; } try { await submitDrawerComment(body, state.commentDrawer.images, scores); elements.drawerCommentBody.value = ''; state.commentDrawer.images.forEach((item) => URL.revokeObjectURL(item.preview)); state.commentDrawer.images = []; if (state.commentDrawer.avatar?.preview) URL.revokeObjectURL(state.commentDrawer.avatar.preview); state.commentDrawer.avatar = null; elements.drawerAvatarPreview.innerHTML = ''; renderDrawerImages(elements.drawerImagePreview, []); toast('评论已发布'); } catch (error) { toast(error.message, true); } });
elements.quickCommentForm.addEventListener('submit', async (event) => { event.preventDefault(); const body = elements.quickCommentBody.value.trim(); if (!body && !state.commentDrawer.quickImages.length) { toast('请填写评论或添加图片', true); return; } try { await submitDrawerComment(body, state.commentDrawer.quickImages); elements.quickCommentBody.value = ''; state.commentDrawer.quickImages.forEach((item) => URL.revokeObjectURL(item.preview)); state.commentDrawer.quickImages = []; renderDrawerImages(elements.quickImagePreview, []); elements.quickCommentDialog.close(); toast('评论已发布'); } catch (error) { toast(error.message, true); } });
elements.drawerCommentList.addEventListener('click', async (event) => { const emoji = event.target.closest('[data-emoji]'); if (emoji) { const textarea = emoji.closest('.reply-form')?.querySelector('textarea'); if (textarea) { textarea.value += emoji.dataset.emoji; textarea.focus(); } return; } const button = event.target.closest('[data-comment-pin], [data-comment-verify]'); if (!button) return; const headers = getAdminHeaders(); if (!headers) return; try { const key = state.commentDrawer.goodsKey; if (button.dataset.commentVerify) { await api(`api/products/${encodeURIComponent(key)}/comments/${button.dataset.commentVerify}/verify`, { method: 'POST', headers, body: JSON.stringify({ verified: button.dataset.verified !== 'true' }) }); await fetchDrawerComments(); return; } const payload = await api(`api/products/${encodeURIComponent(key)}/comments/${button.dataset.commentPin}/pin`, { method: 'POST', headers, body: JSON.stringify({ pinned: button.dataset.pinned !== 'true' }) }); state.commentDrawer.comments.set(payload.comment.id, payload.comment); renderDrawerComments(); } catch (error) { forgetAdminKey(error); toast(error.message, true); } });
elements.drawerCommentList.addEventListener('submit', async (event) => { const form = event.target.closest('.reply-form'); if (!form) return; event.preventDefault(); const body = form.querySelector('textarea').value.trim(); if (!body) return; const headers = state.adminVerified ? getAdminHeaders() : {}; try { const key = state.commentDrawer.goodsKey; const payload = await api(`api/products/${encodeURIComponent(key)}/comments/${form.dataset.replyComment}/replies`, { method: 'POST', headers: headers || {}, body: JSON.stringify({ author: elements.drawerCommentAuthor.value.trim(), body }) }); const comment = state.commentDrawer.comments.get(form.dataset.replyComment); if (comment) { comment.replies = [...(comment.replies || []), payload.reply]; renderDrawerComments(); } } catch (error) { toast(error.message, true); } });
window.addEventListener('popstate', () => closeCommentDrawer(true));
$('#sourceButton').addEventListener('click', () => openSources());

$('#addSourceForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const result = await api('api/sources', {
      method: 'POST',
      body: JSON.stringify({ source: elements.sourceInput.value.trim() }),
    });
    elements.sourceInput.value = '';
    if (result.source?.token) {
      setSourceImportProgress(
        result.source.token,
        result.scan_queued ? 'Added to the refresh queue...' : 'Source added.',
        'running',
      );
    }
    toast(result.scan_queued ? '采集源已加入，服务器正在扫描' : '采集源已加入，等待服务器扫描');
    const payload = await api('api/state');
    state.sources = payload.sources || [];
    state.stats = payload.stats || state.stats;
    const importedSource = state.sources.find((source) => source.token === state.submittedSourceToken);
    if (importedSource?.status === 'ok') {
      setSourceImportProgress(importedSource.token, `Refresh complete: ${Number(importedSource.product_count || 0)} products found.`, 'done');
    } else if (importedSource?.status === 'error') {
      setSourceImportProgress(importedSource.token, `Refresh failed: ${importedSource.last_error || 'unknown error'}`, 'error');
    }
    renderSources(); updateStats();
  } catch (error) { toast(error.message, true); }
});

elements.sourceList.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  const item = event.target.closest('.source-item');
  if (!button || !item) return;
  const token = item.dataset.token;
  const source = state.sources.find((value) => value.token === token);
  if (!source || !state.adminVerified) return;
  const headers = getAdminHeaders();
  if (!headers) return;
  try {
    if (button.dataset.action === 'delete') {
      if (!confirm(`确认删除采集源 ${token}？对应的本地商品记录也会删除。`)) return;
      await api(`api/sources/${encodeURIComponent(token)}`, { method: 'DELETE', headers });
    } else {
      await api(`api/sources/${encodeURIComponent(token)}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ enabled: !source.enabled }),
      });
    }
    await loadState();
  } catch (error) {
    forgetAdminKey(error);
    toast(error.message, true);
  }
});

const savedAdminToken = sessionStorage.getItem('ldxp-admin-key') || '';
if (savedAdminToken) {
  elements.adminTokenInput.value = savedAdminToken;
  void verifyAdminToken(true);
}
updateAdminProxyScanButton();
loadState();
connectEvents();
setInterval(() => {
  for (const [goodsKey, comments] of state.commentPreviews) {
    if (comments.length < 2) continue;
    state.commentCarouselIndex.set(goodsKey, (state.commentCarouselIndex.get(goodsKey) || 0) + 1);
    updateCommentPreview(goodsKey);
  }
}, 5000);
setInterval(() => {
  for (const card of document.querySelectorAll('.product-card .updated')) {
    const product = state.products.get(card.closest('.product-card')?.dataset.key);
    if (product) card.textContent = relativeTime(product.last_seen);
  }
}, 60000);
