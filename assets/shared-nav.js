(function () {
  const navItems = [
    { id: 'mind-map', label: '思维图谱', href: '/mind-map.html' },
    { id: 'matrix', label: '矩阵', href: '/matrix.html' },
    { id: 'timeline', label: '时间线', href: '/vis-timeline.html' },
    { id: 'brand-wall', label: '图片墙', href: '/brand-wall.html' },
    { id: 'awesome', label: 'Awesome Something', href: '/awesome.html' }
  ];

  function renderNav(activePage) {
    const header = document.createElement('header');
    header.className = 'site-nav';
    header.innerHTML = `
      <a class="site-nav__brand" href="/">taste2</a>
      <nav class="site-nav__tabs" aria-label="主导航">
        ${navItems.map((item) => {
          const activeClass = item.id === activePage ? ' is-active' : '';
          return `<a class="site-nav__tab${activeClass}" href="${item.href}">${item.label}</a>`;
        }).join('')}
      </nav>
    `;
    return header;
  }

  function renderPageHeader(title, subtitle) {
    const wrap = document.createElement('section');
    wrap.className = 'page-shell';
    wrap.innerHTML = `
      <div class="page-shell__header">
        <div>
          <h1 class="page-shell__title">${title}</h1>
          ${subtitle ? `<p class="page-shell__subtitle">${subtitle}</p>` : ''}
        </div>
      </div>
    `;
    return wrap;
  }

  window.addEventListener('DOMContentLoaded', () => {
    const activePage = document.body.dataset.navPage || '';
    const mount = document.querySelector('[data-shared-nav-root]');
    const header = renderNav(activePage);
    if (mount) {
      mount.replaceWith(header);
    } else {
      document.body.prepend(header);
    }

    const title = document.body.dataset.pageTitle || '';
    const subtitle = document.body.dataset.pageSubtitle || '';
    const pageHeaderMount = document.querySelector('[data-shared-page-header-root]');
    if (pageHeaderMount && title) {
      pageHeaderMount.replaceWith(renderPageHeader(title, subtitle));
    }
  });
})();
