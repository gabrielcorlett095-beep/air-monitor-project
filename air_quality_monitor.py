import streamlit as st
import requests
import pandas as pd
import psycopg2
import plotly.express as px
st.set_page_config(page_title="Monitor de Ar Pro", page_icon="🌍", layout="centered")

# --- FUNÇÕES ---
def get_color_style(param, value):
    if param == 'pm2_5':
        if value <= 12: return 'mediumseagreen', 'white'
        elif value <= 35: return 'gold', 'black'
        else: return 'tomato', 'white'
    elif param == 'nitrogen_dioxide':
        if value <= 40: return 'mediumseagreen', 'white'
        elif value <= 120: return 'gold', 'black'
        else: return 'tomato', 'white'
    elif param == 'ozone':
        if value <= 100: return 'mediumseagreen', 'white'
        elif value <= 160: return 'gold', 'black'
        else: return 'tomato', 'white'
    return 'gray', 'white'

def salvar_no_banco(cidade, pm25, no2, o3):
    try:
        conn = psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            database=st.secrets["postgres"]["database"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
            port=st.secrets["postgres"]["port"]
        )
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS historico_pesquisas (id SERIAL PRIMARY KEY, cidade VARCHAR(100), pm2_5 NUMERIC, nitrogen_dioxide NUMERIC, ozone NUMERIC, data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
        cursor.execute("INSERT INTO historico_pesquisas (cidade, pm2_5, nitrogen_dioxide, ozone) VALUES (%s, %s, %s, %s)", (cidade, pm25, no2, o3))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except:
        return False

def ler_historico():
    try:
        conn = psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            database=st.secrets["postgres"]["database"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
            port=st.secrets["postgres"]["port"]
        )
        # Busca os dados do banco
        df = pd.read_sql_query("SELECT cidade, pm2_5, nitrogen_dioxide, ozone, data_hora FROM historico_pesquisas ORDER BY data_hora DESC LIMIT 10;", conn)
        conn.close()
        
        # --- CONVERSÃO PARA O FUSO DE BRASÍLIA ---
        # 1. Converte a coluna para datetime e define que ela está em UTC
        df['data_hora'] = pd.to_datetime(df['data_hora']).dt.tz_localize('UTC')
        
        # 2. Converte para o fuso horário de Brasília (America/Sao_Paulo)
        df['data_hora'] = df['data_hora'].dt.tz_convert('America/Sao_Paulo')
        
        # 3. Formata para uma leitura mais limpa (dia/mês hora:minuto)
        df['data_hora'] = df['data_hora'].dt.strftime('%d/%m/%Y %H:%M')
        
        return df
    except:
        return pd.DataFrame()

# --- INTERFACE ---
st.title("🌍 Monitor de Qualidade do Ar Pro")
city = st.text_input("📍 Digite o nome da cidade:")

if st.button("Verificar Qualidade", type="primary"):
    if not city:
        st.warning("Por favor, digite o nome de uma cidade.")
    else:
        with st.spinner(f"Buscando dados para '{city}'..."):
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_res = requests.get(geo_url, params={"name": city, "count": 1, "language": "pt"}).json()
            
            if 'results' in geo_res:
                p = geo_res['results'][0]
                lat, lon, city_name = p['latitude'], p['longitude'], p['name']
                
                # --- CHAMADA DA API ATUALIZADA (COM FORECAST) ---
                aq_res = requests.get(
                    "https://air-quality-api.open-meteo.com/v1/air-quality", 
                    params={
                        "latitude": lat, 
                        "longitude": lon, 
                        "current": "pm2_5,nitrogen_dioxide,ozone", 
                        "hourly": "pm2_5,nitrogen_dioxide,ozone", 
                        "past_days": 1,
                        "forecast_days": 3
                    }
                ).json()
                
                # Exibição dos cards
                curr = aq_res.get('current', {})
                vals = {'pm2_5': curr.get('pm2_5'), 'nitrogen_dioxide': curr.get('nitrogen_dioxide'), 'ozone': curr.get('ozone')}
                rotulos = {'pm2_5': 'Partículas Finas (PM2.5)', 'nitrogen_dioxide': 'Dióxido de Nitrogênio (NO₂)', 'ozone': 'Ozônio (O₃)'}
                
                cols = st.columns(3)
                for (param, val), col in zip(vals.items(), cols):
                    bg, font = get_color_style(param, val)
                    titulo = rotulos.get(param, param)
                    col.markdown(f"<div style='background:{bg}; color:{font}; padding:10px; border-radius:5px; text-align:center;'>{titulo}<br><b>{val} µg/m³</b></div>", unsafe_allow_html=True)
                
                salvar_no_banco(city_name, vals['pm2_5'], vals['nitrogen_dioxide'], vals['ozone'])
                
                # --- GRÁFICO E MAPA ---
                st.subheader("📈 Monitoramento da concentração de poluentes")
                hourly_data = aq_res.get('hourly', {})
                df_hourly = pd.DataFrame({
                    'Horário': pd.to_datetime(hourly_data.get('time')),
                    'Partículas Finas (PM2.5)': hourly_data.get('pm2_5'),
                    'Dióxido de Nitrogênio (NO₂)': hourly_data.get('nitrogen_dioxide'),
                    'Ozônio (O₃)': hourly_data.get('ozone')
                })
                
                # --- GRÁFICO PROFISSIONAL COM PLOTLY ---
                # Transformação para formato "longo"
                df_long = df_hourly.melt(id_vars=['Horário'], 
                                         var_name='Poluente', 
                                         value_name='Concentração')
                
                # Criação da figura
                fig = px.line(df_long, x='Horário', y='Concentração', color='Poluente',
                              labels={'Concentração': 'Concentração (µg/m³)'})
                
                # --- TOOLTIP COM DATA E HORA ---
                
                # O tickformat abaixo garante que o eixo X exiba data e hora
                fig.update_xaxes(tickformat="%d/%m %H:%M")
                
                # No hovertemplate, adicionamos a data (%d/%m) antes do horário (%H:%M)
                fig.update_traces(hovertemplate="<b>%{data.name}</b><br>Data/Hora: %{x|%d/%m %H:%M}<br>Concentração: %{y:.2f} µg/m³")
                
                # Exibição
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("🗺️ Localização")
                st.map(pd.DataFrame({'lat': [lat], 'lon': [lon]}))
            else:
                st.error("Cidade não encontrada.")

# --- HISTÓRICO ---
st.divider()
with st.expander("📂 Ver Histórico de Pesquisas"):
    df_hist = ler_historico()
    if not df_hist.empty: st.table(df_hist)
    else: st.write("Nenhum histórico encontrado.")
