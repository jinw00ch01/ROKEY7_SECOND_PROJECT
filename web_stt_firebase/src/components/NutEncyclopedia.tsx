import { useState } from 'react';

interface NutData {
  nut_name: string;
  daily_serving: string;
  max_limit: string;
  good_pairing: string;
  bad_pairing: string;
  recipe_tip: string;
}

interface NutEncyclopediaProps {
  themeStyle: {
    accentColor: string;
    backgroundColor: string;
    borderColor: string;
    lightColor: string;
    panelBackground: string;
    primaryColor: string;
    secondaryColor: string;
  };
}

export function NutEncyclopedia({ themeStyle }: NutEncyclopediaProps) {
  const [nutData, setNutData] = useState<NutData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchNutInfo = async (name: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`http://localhost:8000/api/nut?name=${encodeURIComponent(name)}`);
      if (!response.ok) {
        throw new Error('정보를 찾을 수 없습니다.');
      }
      const data = await response.json();
      setNutData(data);
    } catch (err: any) {
      setError(err.message || '데이터를 불러오는 데 실패했습니다.');
      setNutData(null);
    } finally {
      setLoading(false);
    }
  };

  const nuts = ['아몬드', '호두', '캐슈넛', '피스타치오'];

  return (
    <div
      style={{
        background: themeStyle.panelBackground,
        border: `1px solid ${themeStyle.borderColor}`,
        borderRadius: 8,
        marginTop: 14,
        width: 440, // Match exact width
        padding: "14px 16px", // Match exact padding
        boxSizing: 'border-box',
        color: 'rgba(235, 248, 255, 0.94)',
        fontFamily: 'sans-serif',
        pointerEvents: 'auto',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2
          style={{
            color: 'inherit',
            fontSize: 24, // Match headline size
            fontWeight: 800,
            letterSpacing: 0,
            lineHeight: 1.15,
            margin: 0,
          }}
        >
          견과류 건강 백과
        </h2>
        <p
          style={{
            color: themeStyle.secondaryColor,
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 0,
            margin: 0,
            textTransform: "uppercase",
          }}
        >
          Encyclopedia
        </p>
      </div>
      
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(4, 1fr)', 
        gap: 8, 
        marginBottom: 12 
      }}>
        {nuts.map(nut => (
          <button
            key={nut}
            onClick={() => fetchNutInfo(nut)}
            style={{
              background: 'rgba(235, 248, 255, 0.12)',
              border: `1px solid ${themeStyle.borderColor}`,
              borderRadius: 6,
              padding: '8px 4px',
              color: 'rgba(235, 248, 255, 0.92)',
              cursor: 'pointer',
              fontSize: 14,
              fontWeight: 700,
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'rgba(235, 248, 255, 0.22)';
              e.currentTarget.style.borderColor = themeStyle.accentColor;
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'rgba(235, 248, 255, 0.12)';
              e.currentTarget.style.borderColor = themeStyle.borderColor;
            }}
          >
            {nut}
          </button>
        ))}
      </div>

      {loading && <p style={{ textAlign: 'center', color: themeStyle.accentColor, fontSize: 13, margin: '8px 0' }}>조회 중...</p>}
      {error && <p style={{ textAlign: 'center', color: '#ffb4b4', fontSize: 13, margin: '8px 0' }}>{error}</p>}

      {nutData && !loading && (
        <div style={{
          background: 'rgba(5, 5, 5, 0.25)',
          borderRadius: 6,
          padding: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          border: `1px solid ${themeStyle.borderColor}33`,
          animation: 'fadeIn 0.2s ease-out',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, borderBottom: `1px solid ${themeStyle.borderColor}33`, paddingBottom: 8 }}>
            <h3 style={{ margin: 0, fontSize: 18, color: themeStyle.accentColor, fontWeight: 800 }}>
              {nutData.nut_name}
            </h3>
            <span style={{ fontSize: 11, color: themeStyle.secondaryColor, fontWeight: 800 }}>INFO</span>
          </div>
          <div style={{ fontSize: 14, lineHeight: 1.4, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px' }}>
            <div>
              <span style={{ color: themeStyle.secondaryColor, fontSize: 11, fontWeight: 800, display: 'block', marginBottom: 2 }}>권장량</span>
              <span>{nutData.daily_serving}</span>
            </div>
            <div>
              <span style={{ color: themeStyle.secondaryColor, fontSize: 11, fontWeight: 800, display: 'block', marginBottom: 2 }}>주의사항</span>
              <span>{nutData.max_limit}</span>
            </div>
            <div>
              <span style={{ color: themeStyle.secondaryColor, fontSize: 11, fontWeight: 800, display: 'block', marginBottom: 2 }}>찰떡궁합</span>
              <span>{nutData.good_pairing}</span>
            </div>
            <div>
              <span style={{ color: themeStyle.secondaryColor, fontSize: 11, fontWeight: 800, display: 'block', marginBottom: 2 }}>활용팁</span>
              <span>{nutData.recipe_tip}</span>
            </div>
          </div>
        </div>
      )}
      
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
