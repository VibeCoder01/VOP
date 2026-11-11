"""Delay image magnification on stable camera containers, not refreshed pixels."""
SCRIPT = r"""(() => {
  const cancel = [];
  for (const stage of document.querySelectorAll('.image-stage, .grid-image-stage')) {
    let timer;
    const clear = () => { clearTimeout(timer); stage.classList.remove('is-magnified'); };
    stage.addEventListener('pointerenter', event => {
      clear();
      if (event.pointerType === 'touch') return;
      timer = setTimeout(() => { if (!document.hidden) stage.classList.add('is-magnified'); }, 1000);
    });
    stage.addEventListener('pointerleave', clear);
    stage.addEventListener('pointercancel', clear);
    cancel.push(clear);
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) cancel.forEach(clear => clear()); });
  window.addEventListener('pagehide', () => cancel.forEach(clear => clear()));
})();"""
