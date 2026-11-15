import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

export default function Chart({ option, onClick, altura = 300 }) {
  const ref = useRef(null);
  const chart = useRef(null);

  useEffect(() => {
    chart.current = echarts.init(ref.current);
    const redimensionar = () => chart.current && chart.current.resize();
    window.addEventListener('resize', redimensionar);
    return () => {
      window.removeEventListener('resize', redimensionar);
      chart.current.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chart.current) return;
    chart.current.off('click');
    if (onClick) chart.current.on('click', (p) => onClick(p.name));
    chart.current.setOption(option, true);
  }, [option, onClick]);

  return <div ref={ref} style={{ width: '100%', height: altura }} />;
}