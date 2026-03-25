export const NEO_COLORS = {
  black: '#111111',
  parchment: '#F4F0EB',
  dark: '#1E1E1E',
  sage: '#8A9A86',
  mustard: '#D9B756',
  blue: '#7B8B9E',
  white: '#FFFFFF',
} as const;

export const echartsTheme = {
  color: [NEO_COLORS.blue, NEO_COLORS.sage, NEO_COLORS.mustard, NEO_COLORS.dark, NEO_COLORS.black],
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: "'IBM Plex Mono', monospace",
    color: NEO_COLORS.black,
  },
  title: {
    textStyle: {
      fontFamily: "'IBM Plex Mono', monospace",
      fontWeight: 700,
      fontSize: 14,
      color: NEO_COLORS.black,
    },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: NEO_COLORS.black, width: 2 } },
    axisTick: { lineStyle: { color: NEO_COLORS.black, width: 2 } },
    axisLabel: {
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 11,
      color: NEO_COLORS.black,
    },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: NEO_COLORS.black, width: 2 } },
    axisTick: { lineStyle: { color: NEO_COLORS.black, width: 2 } },
    axisLabel: {
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 11,
      color: NEO_COLORS.black,
    },
    splitLine: {
      lineStyle: { color: NEO_COLORS.black, opacity: 0.1, type: 'dashed' },
    },
  },
};

export function buildBarChartOption(
  categories: string[],
  values: number[],
  opts?: { horizontal?: boolean; highlightMax?: boolean }
) {
  const maxVal = Math.max(...values);
  const colors = values.map((v) =>
    opts?.highlightMax && v === maxVal ? NEO_COLORS.mustard : NEO_COLORS.blue
  );

  const axis = {
    type: 'category' as const,
    data: categories,
    axisLine: { lineStyle: { color: NEO_COLORS.black, width: 2 } },
    axisTick: { show: false },
    axisLabel: {
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 10,
      color: NEO_COLORS.black,
    },
  };
  const valAxis = {
    type: 'value' as const,
    axisLine: { lineStyle: { color: NEO_COLORS.black, width: 2 } },
    axisTick: { show: false },
    axisLabel: {
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 10,
      color: NEO_COLORS.black,
    },
    splitLine: { lineStyle: { color: NEO_COLORS.black, opacity: 0.08, type: 'dashed' as const } },
  };

  return {
    grid: { left: 60, right: 20, top: 10, bottom: 40 },
    xAxis: opts?.horizontal ? valAxis : axis,
    yAxis: opts?.horizontal ? axis : valAxis,
    series: [
      {
        type: 'bar',
        data: values.map((v, i) => ({
          value: v,
          itemStyle: { color: colors[i], borderColor: NEO_COLORS.black, borderWidth: 1 },
        })),
        barWidth: '60%',
        emphasis: {
          itemStyle: { color: NEO_COLORS.sage, borderColor: NEO_COLORS.black, borderWidth: 2 },
        },
      },
    ],
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: NEO_COLORS.black,
      borderColor: NEO_COLORS.black,
      textStyle: { color: NEO_COLORS.parchment, fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 },
    },
    animation: false,
  };
}

export function buildRadarOption(indicators: { name: string; max: number }[], values: number[]) {
  return {
    radar: {
      indicator: indicators,
      shape: 'polygon' as const,
      axisLine: { lineStyle: { color: NEO_COLORS.black, opacity: 0.2 } },
      splitLine: { lineStyle: { color: NEO_COLORS.black, opacity: 0.1 } },
      splitArea: { show: false },
      axisName: {
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 10,
        color: NEO_COLORS.black,
        fontWeight: 700,
      },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: values,
            areaStyle: { color: NEO_COLORS.blue, opacity: 0.15 },
            lineStyle: { color: NEO_COLORS.black, width: 2 },
            symbol: 'circle',
            symbolSize: 6,
            itemStyle: { color: NEO_COLORS.black, borderWidth: 0 },
          },
        ],
      },
    ],
    animation: false,
  };
}

export function buildPieOption(data: { name: string; value: number }[]) {
  return {
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '50%'],
        data: data.map((d, i) => ({
          ...d,
          itemStyle: {
            color: [NEO_COLORS.blue, NEO_COLORS.sage, NEO_COLORS.mustard, NEO_COLORS.dark, NEO_COLORS.black][i % 5],
            borderColor: NEO_COLORS.black,
            borderWidth: 2,
          },
        })),
        label: {
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 10,
          color: NEO_COLORS.black,
          formatter: '{b}\n{d}%',
        },
        emphasis: {
          itemStyle: { borderWidth: 3 },
        },
      },
    ],
    tooltip: {
      backgroundColor: NEO_COLORS.black,
      borderColor: NEO_COLORS.black,
      textStyle: { color: NEO_COLORS.parchment, fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 },
    },
    animation: false,
  };
}
