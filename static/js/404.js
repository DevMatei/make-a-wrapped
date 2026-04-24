const VINYL_MESSAGES = [
    "Looks like this record has skipped a few beats.",
    "This track is missing from the album.",
    "Oops! Wrong side of the vinyl.",
    "Sabrina Carpenter is the best artist, buttt this page won't appear because of her :("
];

function init404Page() {
    const messageEl = document.querySelector('.error-message');
    const vinylEl = document.querySelector('.vinyl');

    messageEl.textContent = VINYL_MESSAGES[Math.floor(Math.random() * VINYL_MESSAGES.length)];

    let rotation = 0;
    const spin = () => {
        rotation += 2;
        vinylEl.style.transform = `rotate(${rotation}deg)`;
        requestAnimationFrame(spin);
    };
    requestAnimationFrame(spin);
}

// Make sure the DOM is loaded before initializing 
document.addEventListener('DOMContentLoaded', init404Page);

console.log('%c👋 Howdy developer! \n\n%cThis is an open-source project by DevMatei\n\n%cGitHub:%chttps://github.com/devmatei/make-a-wrapped',
  'font-size: 16px; font-weight: bold; color: #6366f1;',
  'font-size: 14px; color: #4b5563;',
  'font-size: 15px; color: #4b5563;',
  'font-size: 15px; color: #2563eb; text-decoration: underline;'
)