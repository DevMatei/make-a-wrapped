const VINYL_MESSAGES = [
    "looks like this record skipped a few beats.",
    "this track is missing from the album.",
    "oops, wrong side of the vinyl."
];

function init404Page() {
    const messageEl = document.querySelector('.error-message');
    const vinylEl = document.querySelector('.vinyl');

    if (messageEl) {
        messageEl.textContent = VINYL_MESSAGES[Math.floor(Math.random() * VINYL_MESSAGES.length)];
    }

    if (!vinylEl) {
        return;
    }
    const motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    let rotation = 0;
    let frame = null;
    const spin = () => {
        rotation = (rotation + 2) % 360;
        vinylEl.style.transform = `rotate(${rotation}deg)`;
        frame = requestAnimationFrame(spin);
    };
    const update = () => {
        if (motionQuery && motionQuery.matches) {
            if (frame !== null) {
                cancelAnimationFrame(frame);
                frame = null;
            }
            vinylEl.style.transform = '';
        } else if (frame === null) {
            frame = requestAnimationFrame(spin);
        }
    };
    update();
    if (motionQuery && typeof motionQuery.addEventListener === 'function') {
        motionQuery.addEventListener('change', update);
    }
}

// Make sure the DOM is loaded before initializing
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init404Page);
} else {
    init404Page();
}

console.log('%c👋 Howdy developer! \n\n%cThis is an open-source project by DevMatei\n\n%cGitHub:%chttps://github.com/devmatei/make-a-wrapped',
  'font-size: 16px; font-weight: bold; color: #6366f1;',
  'font-size: 14px; color: #4b5563;',
  'font-size: 15px; color: #4b5563;',
  'font-size: 15px; color: #2563eb; text-decoration: underline;'
)