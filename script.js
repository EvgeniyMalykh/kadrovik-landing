// Theme toggle
(function () {
  const toggle = document.querySelector('[data-theme-toggle]');
  const root = document.documentElement;
  let theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  root.setAttribute('data-theme', theme);

  function updateIcon() {
    if (!toggle) return;
    toggle.innerHTML = theme === 'dark'
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }

  toggle && toggle.addEventListener('click', () => {
    theme = theme === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', theme);
    updateIcon();
  });
  updateIcon();
})();

// Mobile menu
(function () {
  const burger = document.getElementById('burger');
  const menu = document.getElementById('mobileMenu');
  if (!burger || !menu) return;

  burger.addEventListener('click', () => {
    menu.classList.toggle('open');
    burger.setAttribute('aria-expanded', menu.classList.contains('open'));
  });

  menu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      menu.classList.remove('open');
    });
  });
})();

// Sticky header shadow
(function () {
  const header = document.getElementById('header');
  if (!header) return;
  window.addEventListener('scroll', () => {
    if (window.scrollY > 10) {
      header.style.boxShadow = '0 2px 16px rgba(0,0,0,0.08)';
    } else {
      header.style.boxShadow = '';
    }
  }, { passive: true });
})();

// Intersection Observer animations
(function () {
  const els = document.querySelectorAll('.feature-card, .pain-card, .step, .doc-item, .pricing-card, .faq-item');
  if (!('IntersectionObserver' in window)) return;

  const obs = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '0';
        entry.target.style.transform = 'translateY(20px)';
        setTimeout(() => {
          entry.target.style.transition = 'opacity 0.5s ease, transform 0.5s cubic-bezier(0.16,1,0.3,1)';
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
        }, 60);
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  els.forEach(el => obs.observe(el));
})();

// Billing period toggle
(function () {
  document.querySelectorAll('.billing-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.billing-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const isAnnual = btn.dataset.period === 'annual';
      document.querySelectorAll('.price-monthly').forEach(el => el.style.display = isAnnual ? 'none' : 'block');
      document.querySelectorAll('.price-annual').forEach(el => el.style.display = isAnnual ? 'block' : 'none');
    });
  });
})();

// Waitlist form
(function () {
  const SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbyjBzH-oPBtC-pJGZ8UCgncTpc21Rs1xCDY4fwpb7URZOdS7ZY0rwEB_1RGcmMb1vUDHg/exec';

  const form = document.getElementById('waitlistForm');
  const success = document.getElementById('formSuccess');
  if (!form || !success) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.textContent = 'Отправляем...';
    btn.disabled = true;

    const data = {
      name: form.querySelector('#name').value.trim(),
      email: form.querySelector('#email').value.trim(),
      telegram: form.querySelector('#telegram').value.trim(),
      employees: form.querySelector('#employees').value,
      source: 'Лендинг'
    };

    try {
      await fetch(SCRIPT_URL, {
        method: 'POST',
        mode: 'no-cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      // no-cors всегда возвращает opaque response — считаем успехом
      form.style.display = 'none';
      success.style.display = 'block';
    } catch (err) {
      btn.textContent = originalText;
      btn.disabled = false;
      alert('Ошибка отправки. Попробуйте ещё раз или напишите нам напрямую.');
    }
  });
})();
