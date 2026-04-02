import './style.css';

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function initHeaderScroll(): void {
  const header = document.getElementById('site-header');
  if (!header) return;

  const onScroll = (): void => {
    header.classList.toggle('scrolled', window.scrollY > 10);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

function initMobileMenu(): void {
  const btn = document.querySelector<HTMLButtonElement>('.mobile-menu-btn');
  const nav = document.querySelector<HTMLElement>('.main-nav');
  if (!btn || !nav) return;

  btn.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('open');
    btn.classList.toggle('open', isOpen);
    btn.setAttribute('aria-expanded', String(isOpen));
  });

  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('open');
      btn.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    });
  });
}

interface TerminalLine {
  text: string;
  className?: string;
  typeSpeed?: number;
  instant?: boolean;
  pauseAfter?: number;
}

function buildSensorBar(filled: number, total: number): string {
  const full = '\u2588'.repeat(filled);
  const empty = '\u2591'.repeat(total - filled);
  return `<span class="term-bar">${full}</span><span class="term-bar-empty">${empty}</span>`;
}

function getTerminalScript(): TerminalLine[] {
  return [
    { text: '<span class="term-cmd">&gt; Connecting to OBD adapter...</span>', instant: true, pauseAfter: 600 },
    { text: '<span class="term-cmd">&gt; Port:</span> <span class="term-value">/dev/ttyUSB0</span>  <span class="term-cmd">Protocol:</span> <span class="term-value">ISO 15765-4 (CAN)</span>', instant: true, pauseAfter: 400 },
    { text: '<span class="term-cmd">&gt; Reading sensors...</span>', instant: true, pauseAfter: 500 },
    { text: '', instant: true, pauseAfter: 100 },
    { text: `  <span class="term-label">RPM</span>          ${buildSensorBar(8, 10)}  <span class="term-value">2,847 rpm</span>`, instant: true, pauseAfter: 120 },
    { text: `  <span class="term-label">COOLANT</span>      ${buildSensorBar(10, 10)}  <span class="term-value">94°C</span>`, instant: true, pauseAfter: 120 },
    { text: `  <span class="term-label">ENGINE LOAD</span>  ${buildSensorBar(7, 10)}  <span class="term-value">71%</span>`, instant: true, pauseAfter: 120 },
    { text: `  <span class="term-label">FUEL TRIM</span>    ${buildSensorBar(2, 10)}  <span class="term-value">+2.3%</span>`, instant: true, pauseAfter: 120 },
    { text: `  <span class="term-label">BATTERY</span>      ${buildSensorBar(9, 10)}  <span class="term-value">14.1V</span>`, instant: true, pauseAfter: 500 },
    { text: '', instant: true, pauseAfter: 100 },
    { text: '<span class="term-cmd">&gt; Reading fault codes...</span>', instant: true, pauseAfter: 600 },
    { text: '  <span class="term-dtc-code">P0420</span>  <span class="term-dtc-desc">Catalyst efficiency (Bank 1)</span>     <span class="term-warning">\u26A0 warning</span>', instant: true, pauseAfter: 300 },
    { text: '  <span class="term-dtc-code">P0171</span>  <span class="term-dtc-desc">System too lean (Bank 1)</span>         <span class="term-warning">\u26A0 warning</span>', instant: true, pauseAfter: 500 },
    { text: '', instant: true, pauseAfter: 100 },
    { text: '<span class="term-cmd">&gt; Running AI diagnosis...</span>', instant: true, pauseAfter: 1200 },
    { text: '  <span class="term-success">\u2713 Analysis complete</span> — <span class="term-warning">severity: WARNING</span>', instant: true, pauseAfter: 0 },
  ];
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function typewriteLine(container: HTMLElement, html: string, speed: number): Promise<void> {
  const tempEl = document.createElement('span');
  tempEl.innerHTML = html;
  const plainText = tempEl.textContent ?? '';

  const lineEl = document.createElement('div');
  container.appendChild(lineEl);

  let charIndex = 0;
  while (charIndex < plainText.length) {
    lineEl.innerHTML = html.substring(0, findHtmlIndex(html, charIndex + 1));
    charIndex++;
    await sleep(speed);
  }
  lineEl.innerHTML = html;
}

function findHtmlIndex(html: string, charTarget: number): number {
  let charCount = 0;
  let inTag = false;
  let inEntity = false;

  for (let i = 0; i < html.length; i++) {
    if (html[i] === '<') { inTag = true; continue; }
    if (html[i] === '>') { inTag = false; continue; }
    if (inTag) continue;

    if (html[i] === '&') { inEntity = true; }
    if (inEntity) {
      if (html[i] === ';') {
        inEntity = false;
        charCount++;
        if (charCount >= charTarget) return i + 1;
      }
      continue;
    }

    charCount++;
    if (charCount >= charTarget) return i + 1;
  }
  return html.length;
}

async function runTerminalAnimation(): Promise<void> {
  const output = document.getElementById('terminal-output');
  const cursor = document.getElementById('terminal-cursor');
  if (!output || !cursor) return;

  if (prefersReducedMotion()) {
    output.innerHTML = '';
    for (const line of getTerminalScript()) {
      const lineEl = document.createElement('div');
      lineEl.innerHTML = line.text;
      output.appendChild(lineEl);
    }
    cursor.style.display = 'none';
    return;
  }

  const script = getTerminalScript();

  const runOnce = async (): Promise<void> => {
    output.innerHTML = '';
    cursor.style.display = 'inline';

    for (const line of script) {
      if (line.instant) {
        const lineEl = document.createElement('div');
        lineEl.innerHTML = line.text;
        output.appendChild(lineEl);
      } else {
        await typewriteLine(output, line.text, line.typeSpeed ?? 20);
      }

      const scrollParent = output.parentElement;
      if (scrollParent) {
        scrollParent.scrollTop = scrollParent.scrollHeight;
      }

      if (line.pauseAfter) {
        await sleep(line.pauseAfter);
      }
    }

    await sleep(8000);
  };

  while (true) {
    await runOnce();
  }
}

function initSmoothScroll(): void {
  document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      const targetId = anchor.getAttribute('href');
      if (!targetId || targetId === '#') return;

      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initHeaderScroll();
  initMobileMenu();
  initSmoothScroll();
  void runTerminalAnimation();
});
