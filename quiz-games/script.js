document.addEventListener('DOMContentLoaded', () => {

const players = [
  {
    name: "Lionel Messi",
    nationality: "Argentina",
    international: { caps: 180, goals: 106, firstCap: "2005-08-17", lastCap: "2024-06-xx" },
    clubs: [
      { club: "Newell's Old Boys (youth)", from: 1995, to: 2000, apps: 0, goals: 0 },
      { club: "FC Barcelona", from: 2004, to: 2021, apps: 778, goals: 672 },
      { club: "Paris Saint-Germain", from: 2021, to: 2023, apps: 75, goals: 32 },
      { club: "Inter Miami", from: 2023, to: null, apps: 50, goals: 25 }
    ]
  },
  {
    name: "Cristiano Ronaldo",
    nationality: "Portugal",
    international: { caps: 205, goals: 128, firstCap: "2003-08-20", lastCap: "2024-06-xx" },
    clubs: [
      { club: "Sporting CP", from: 2002, to: 2003, apps: 31, goals: 5 },
      { club: "Manchester United", from: 2003, to: 2009, apps: 292, goals: 118 },
      { club: "Real Madrid", from: 2009, to: 2018, apps: 438, goals: 450 },
      { club: "Juventus", from: 2018, to: 2021, apps: 134, goals: 101 },
      { club: "Manchester United", from: 2021, to: 2022, apps: 54, goals: 27 },
      { club: "Al Nassr", from: 2023, to: null, apps: 60, goals: 54 }
    ]
  }
];

const careerGrid = document.getElementById('careerGrid');
const revealBtn = document.getElementById('revealBtn');
const submitBtn = document.getElementById('submitBtn');
const skipBtn = document.getElementById('skipBtn');
const guessInput = document.getElementById('guessInput');
const resultEl = document.getElementById('result');
const revealInfo = document.getElementById('revealInfo');
const intCard = document.getElementById('intCard');
const totalScoreEl = document.getElementById('totalScore');
const historyEl = document.getElementById('history');
const guessLog = document.getElementById('guessLog');

let order = [], idx = 0, current = null;
let revealedClubs = 1, postRevealStage = 0, guessCount = 0, totalScore = 0;
let thisRoundGuesses = [];

const POST_REVEAL_TOTAL = 90;
const POST_REVEAL_STEPS = 5;
const POST_REVEAL_COST = POST_REVEAL_TOTAL / POST_REVEAL_STEPS;
const MULTIPLIERS = [10,5,4.5,4,3.5,3,2.5,2,1.5,1.2];

function shuffle(a){ return a.slice().sort(()=>Math.random()-0.5); }
function properCase(s){ return s.replace(/\w[\w']*/g, t=>t.charAt(0).toUpperCase()+t.substr(1).toLowerCase()); }
function levenshtein(a,b){
  a=a.toLowerCase(); b=b.toLowerCase();
  const m=a.length,n=b.length;
  const dp=Array.from({length:m+1},()=>Array(n+1).fill(0));
  for(let i=0;i<=m;i++) dp[i][0]=i;
  for(let j=0;j<=n;j++) dp[0][j]=j;
  for(let i=1;i<=m;i++){
    for(let j=1;j<=n;j++){
      const cost=a[i-1]===b[j-1]?0:1;
      dp[i][j]=Math.min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost);
    }
  }
  return dp[m][n];
}
function similarity(a,b){ return (1 - levenshtein(a,b)/Math.max(a.length,b.length))*100; }
function round2(v){ return Math.round(v*100)/100; }

function initOrder(){ order = shuffle(players); idx=0; }
function nextPlayer(){
  current = JSON.parse(JSON.stringify(order[idx]));
  idx=(idx+1)%order.length;
  revealedClubs=1; postRevealStage=0; guessCount=0; thisRoundGuesses=[];
  renderGrid(); resultEl.textContent='—';
}

function renderGrid(){
  if(!careerGrid) return;
  const clubs=current.clubs;
  let rows=[];
  for(let i=0;i<clubs.length;i++){
    const revealed=i<revealedClubs;
    const clubCell=`<div class="club-cell ${revealed?'':'blurred'}">${revealed?clubs[i].club:'██████'}</div>`;
    const appsCellClass=(revealedClubs===clubs.length && postRevealStage>=1)?'':'blurred';
    const appsContent=(revealedClubs===clubs.length && postRevealStage>=1)?`${clubs[i].apps} apps / ${clubs[i].goals} goals`:'██████';
    const appsCell=`<div class="club-cell ${appsCellClass}">${appsContent}</div>`;
    const dateCellClass=(revealedClubs===clubs.length && postRevealStage>=2)?'':'blurred';
    const dateContent=(revealedClubs===clubs.length && postRevealStage>=2)?`${clubs[i].from} – ${clubs[i].to?clubs[i].to:'Present'}`:'██████';
    const dateCell=`<div class="club-cell ${dateCellClass}">${dateContent}</div>`;
    rows.push(`<div class="career-row">${clubCell}${appsCell}${dateCell}</div>`);
  }
  careerGrid.innerHTML=`<div class="career-col-title">Club</div><div class="career-col-title">Apps / Goals</div><div class="career-col-title">Dates</div>${rows.join('')}`;
  updateRevealInfo(); renderIntlCard();
}

function renderIntlCard(){
  if(!intCard) return;
  const natEl=intCard.querySelector('[data-field="nationality"]');
  const intlEl=intCard.querySelector('[data-field="intl"]');
  const datesEl=intCard.querySelector('[data-field="capsDates"]');
  if(natEl){ natEl.classList.toggle('blurred', !(revealedClubs===current.clubs.length && postRevealStage>=3)); natEl.querySelector('.value').textContent = (revealedClubs===current.clubs.length && postRevealStage>=3)?current.nationality:'████'; }
  if(intlEl){ intlEl.classList.toggle('blurred', !(revealedClubs===current.clubs.length && postRevealStage>=4)); intlEl.querySelector('.value').textContent = (revealedClubs===current.clubs.length && postRevealStage>=4)?`${current.international.caps} / ${current.international.goals}`:'████'; }
  if(datesEl){ datesEl.classList.toggle('blurred', !(revealedClubs===current.clubs.length && postRevealStage>=5)); datesEl.querySelector('.value').textContent = (revealedClubs===current.clubs.length && postRevealStage>=5)?`${current.international.firstCap} — ${current.international.lastCap}`:'████'; }
}

function clubScore(){ const N=current.clubs.length; return round2(Math.max(0,100-(revealedClubs-1)*(100/N))); }
function postScore(){ return round2(Math.max(0,POST_REVEAL_TOTAL-(postRevealStage*POST_REVEAL_COST))); }
function totalBase(){ return clubScore()+postScore(); }
function mult(n){ return n<=0?1:(n<=MULTIPLIERS.length?MULTIPLIERS[n-1]:1); }
function finalScore(){ return Math.max(0,Math.round(totalBase()*mult(guessCount))); }

function updateRevealInfo(){
  if(!revealInfo || !revealBtn) return;
  const clubsLeft=current.clubs.length-revealedClubs;
  let label='', cost=0;
  if(clubsLeft>0){ const N=current.clubs.length; label='Reveal next club'; cost=Math.round(100/N); }
  else { const nextStage=postRevealStage+1; 
    if(nextStage<=POST_REVEAL_STEPS){ const names=["Apps & Goals","Club Dates","Nationality","Intl Caps/Goals","First/Last Cap Dates"]; 
      label=`Reveal ${names[nextStage-1]}`; cost=POST_REVEAL_COST; 
    } else { label='Nothing left to reveal'; cost=0; } 
  }
  revealInfo.textContent=`${label} — -${cost} pts`; revealBtn.textContent=`${label} — -${cost} pts`;
}

function revealNext(){ if(revealedClubs<current.clubs.length) revealedClubs++; else if(postRevealStage<POST_REVEAL_STEPS) postRevealStage++; renderGrid(); }

function logGuess(txt){ if(!guessLog) return; const n=document.createElement('div'); n.className='log-entry'; n.textContent=txt; guessLog.prepend(n); }
function logHistory(txt){ if(!historyEl) return; const n=document.createElement('div'); n.className='log-entry'; n.innerHTML=txt; historyEl.prepend(n); }
function normalizeGuess(s){ return s.trim(); }

function submitGuess(){
  if(!guessInput) return;
  const raw=guessInput.value;
  const normalized=normalizeGuess(raw);
  if(normalized.length<3){ if(resultEl) resultEl.textContent='Guess at least 3 characters.'; return; }

  guessCount++; thisRoundGuesses.push(normalized); logGuess(properCase(normalized));
  guessInput.value='';

  const sim=similarity(normalized,current.name);
  const exact=current.name.toLowerCase().includes(normalized.toLowerCase());
  const ok=exact || sim>=85;

  if(ok){
    const pts=finalScore(); totalScore+=pts; if(totalScoreEl) totalScoreEl.textContent=totalScore;
    highlightCorrect(pts);
    const clubsRevealedText=`${revealedClubs} club${revealedClubs>1?'s':''}`;
    logHistory(`<strong>${properCase(current.name)}</strong> guessed after ${clubsRevealedText} (${guessCount} guesses). +${pts} pts.`);
    setTimeout(()=>nextPlayer(),900);
  } else if(resultEl){ resultEl.textContent='Incorrect.'; }
}

function highlightCorrect(points){
  if(!careerGrid) return;
  const revealedCells=careerGrid.querySelectorAll('.club-cell');
  revealedCells.forEach(c=>{ if(c.classList.contains('blurred')) return; c.classList.add('correct-highlight'); setTimeout(()=>c.classList.remove('correct-highlight'),700); });
  const pop=document.createElement('div'); pop.className='pop'; pop.textContent=`+${points}`;
  const wrap=document.createElement('div'); wrap.className='score-pop'; wrap.appendChild(pop); totalScoreEl.parentNode.appendChild(wrap);
  setTimeout(()=>wrap.remove(),1000);
  if(resultEl) resultEl.textContent=`Correct! +${points} pts`;
}

if(revealBtn) revealBtn.addEventListener('click', ()=>{ revealNext(); updateRevealInfo(); });
if(submitBtn) submitBtn.addEventListener('click', ()=>{ submitGuess(); updateRevealInfo(); });
if(skipBtn) skipBtn.addEventListener('click', ()=>{ nextPlayer(); updateRevealInfo(); });
if(guessInput) guessInput.addEventListener('keydown', e=>{ if(e.key==='Enter'){ submitGuess(); updateRevealInfo(); } });

initOrder(); nextPlayer(); updateRevealInfo();

});
