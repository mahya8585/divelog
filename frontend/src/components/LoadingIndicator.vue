<template>
  <div class="loading-indicator" role="status" aria-live="polite">
    <div class="nudibranch-track" aria-hidden="true">
      <svg class="nudibranch" viewBox="0 0 140 80" xmlns="http://www.w3.org/2000/svg">
        <g class="nudibranch-body">
          <path
            class="body-shape"
            d="M16 44C16 30 32 20 53 20H78C96 20 111 28 118 40C121 45 121 51 118 56C111 68 96 76 78 76H53C32 76 16 65 16 52C16 49 16 47 16 44Z"
          />
          <path
            class="body-stripe"
            d="M28 53C38 57 49 60 63 60C80 60 93 55 103 49"
          />
          <path class="antenna" d="M106 30C111 20 117 15 125 14" />
          <path class="antenna" d="M98 27C101 18 105 12 111 9" />
        </g>
      </svg>
    </div>
    <p class="loading-text">{{ text }}</p>
  </div>
</template>

<script setup>
defineProps({
  text: {
    type: String,
    default: 'データ取得中',
  },
})
</script>

<style scoped>
.loading-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.55rem;
}

.nudibranch-track {
  width: min(240px, 92vw);
  overflow: hidden;
}

.nudibranch {
  width: 110px;
  height: auto;
  animation: crawl-right 2.5s ease-in-out infinite;
}

.nudibranch-body {
  transform-origin: 50% 58%;
  animation: wiggle 1.15s ease-in-out infinite;
}

.body-shape {
  fill: var(--ocean-mid);
}

.body-stripe,
.antenna {
  stroke: var(--ocean-teal);
  stroke-width: 3.2;
  stroke-linecap: round;
  fill: none;
}

.loading-text {
  margin: 0;
  color: var(--ocean-mid);
  font-weight: 600;
  letter-spacing: 0.03em;
}

@keyframes crawl-right {
  0%   { transform: translateX(-28%); }
  50%  { transform: translateX(58%); }
  100% { transform: translateX(138%); }
}

@keyframes wiggle {
  0%, 100% { transform: translateY(0) scaleX(1) rotate(0deg); }
  25%      { transform: translateY(-1px) scaleX(1.02) rotate(-1.2deg); }
  50%      { transform: translateY(1px) scaleX(.98) rotate(1deg); }
  75%      { transform: translateY(-1px) scaleX(1.01) rotate(-.8deg); }
}
</style>
