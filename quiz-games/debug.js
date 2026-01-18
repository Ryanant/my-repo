// All-in-one debug script for CareerPath game
(function() {
  console.log('=== CareerPath Debug Script Loaded ===');

  // List of critical element IDs
  const ids = [
    'careerGrid', 'revealBtn', 'submitBtn', 'skipBtn',
    'guessInput', 'result', 'revealInfo', 'intCard',
    'totalScore', 'history', 'guessLog'
  ];

  // Check existence and highlight missing elements
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      console.log(`Element "${id}": FOUND ✅`);
      el.style.outline = '2px solid green'; // optional visual
    } else {
      console.log(`Element "${id}": MISSING ❌`);
      // create a placeholder div to show missing element
      const placeholder = document.createElement('div');
      placeholder.textContent = `MISSING: ${id}`;
      placeholder.style.color = 'white';
      placeholder.style.background = 'red';
      placeholder.style.padding = '5px';
      placeholder.style.margin = '2px';
      placeholder.style.fontWeight = 'bold';
      document.body.prepend(placeholder);
    }
  });

  // Test button clicks
  ['revealBtn', 'submitBtn', 'skipBtn'].forEach(id => {
    const btn = document.getElementById(id);
    if(btn) {
      btn.addEventListener('click', () => console.log(`Button "${id}" clicked! ✅`));
      console.log(`Event listener attached to "${id}"`);
    } else {
      console.log(`Cannot attach event to "${id}" — element missing ❌`);
    }
  });

  // Test input keypress
  const guessInput = document.getElementById('guessInput');
  if(guessInput){
    guessInput.addEventListener('keydown', (e) => {
      console.log(`Key pressed in guessInput: "${e.key}"`);
    });
    console.log('Input key listener attached ✅');
  } else {
    console.log('guessInput element missing ❌');
  }

  // Global error handling
  window.addEventListener('error', function(e){
    console.error('JavaScript error detected:', e.message, 'at', e.filename, 'line', e.lineno);
  });

  window.addEventListener('unhandledrejection', function(e){
    console.error('Unhandled Promise rejection:', e.reason);
  });

  console.log('=== Debug script initialized ===');
})();
