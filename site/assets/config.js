// ===== CONFIGURAÇÃO DO SITE (edite só este arquivo) =====
window.SITE_CONFIG = {
  // WhatsApp com DDI 55 + DDD + número, só dígitos. PROVISÓRIO: troque pelo número real.
  whatsapp: '5521900000000',
  whatsappProvisorio: true,      // mude para false quando colocar o número real
  nomeEmpresa: 'Ambiental Costa',
  // Registro no CREA-RJ e responsável técnico (aparecem no rodapé). PREENCHER.
  creaRegistro: '',
  responsavelTecnico: '',

  // Área restrita (Supabase). Preencha com os dados do SEU projeto Supabase:
  // Project Settings > API > Project URL e "anon public key".
  // A chave "anon" é pública por natureza; a proteção vem das regras RLS do banco.
  // NUNCA coloque aqui a chave "service_role".
  supabaseUrl: 'https://mxfgezgmyowqjmaibdkl.supabase.co',
  supabaseAnonKey: ''
};
