// Synthetic sample data for the cross-source cards (social / INDECOPI / SBS DSC).
// SAMPLE ONLY — every card that renders this MUST show the "datos de muestra"
// badge. URLs are obviously-fake placeholders; they are never presented as
// real links. Real cards (reading social_signals / indecopi_cases) do NOT use
// this module and do NOT carry the badge.

export interface SocialSample {
  fecha: string;
  plataforma: string;
  tendencia: string;
  menciones: number;
  indicador: string;
  enlace: string;
}

export const SOCIAL_SAMPLE: SocialSample[] = [
  { fecha: '2026-05-28', plataforma: 'Twitter/X', tendencia: 'Tarjeta clonada en cajeros', menciones: 142, indicador: 'Phishing', enlace: 'https://x.com/ejemplo/status/1001' },
  { fecha: '2026-05-28', plataforma: 'Facebook', tendencia: 'App falsa de banca móvil', menciones: 98, indicador: 'Aplicación falsa', enlace: 'https://facebook.com/ejemplo/posts/1002' },
  { fecha: '2026-05-27', plataforma: 'Reddit', tendencia: 'Llamadas suplantando ejecutivos', menciones: 64, indicador: 'Agente falso', enlace: 'https://reddit.com/r/ejemplo/1003' },
  { fecha: '2026-05-27', plataforma: 'Twitter/X', tendencia: 'Cobros no reconocidos', menciones: 57, indicador: 'Consumo no autorizado', enlace: 'https://x.com/ejemplo/status/1004' },
  { fecha: '2026-05-26', plataforma: 'TikTok', tendencia: 'Phishing por SMS (smishing)', menciones: 51, indicador: 'Phishing', enlace: 'https://tiktok.com/@ejemplo/video/1005' },
  { fecha: '2026-05-26', plataforma: 'Facebook', tendencia: 'Comisiones ocultas en tarjeta', menciones: 43, indicador: 'Cargo no autorizado', enlace: 'https://facebook.com/ejemplo/posts/1006' },
  { fecha: '2026-05-25', plataforma: 'Reddit', tendencia: 'Demora en reversión de cargo', menciones: 38, indicador: 'Estafa', enlace: 'https://reddit.com/r/ejemplo/1007' },
  { fecha: '2026-05-25', plataforma: 'Twitter/X', tendencia: 'Transferencia no autorizada', menciones: 34, indicador: 'Consumo no autorizado', enlace: 'https://x.com/ejemplo/status/1008' },
  { fecha: '2026-05-24', plataforma: 'Facebook', tendencia: 'Enlaces de premios falsos', menciones: 29, indicador: 'Phishing', enlace: 'https://facebook.com/ejemplo/posts/1009' },
  { fecha: '2026-05-24', plataforma: 'TikTok', tendencia: 'Suplantación de marca', menciones: 26, indicador: 'Aplicación falsa', enlace: 'https://tiktok.com/@ejemplo/video/1010' },
  { fecha: '2026-05-23', plataforma: 'Twitter/X', tendencia: 'QR de pago manipulado', menciones: 22, indicador: 'Estafa', enlace: 'https://x.com/ejemplo/status/1011' },
  { fecha: '2026-05-23', plataforma: 'Reddit', tendencia: 'Cobro doble en compras online', menciones: 18, indicador: 'Consumo no autorizado', enlace: 'https://reddit.com/r/ejemplo/1012' },
];

export interface IndecopiSample {
  expediente: string;
  categoria: string;
  institucion: string;
  estado: string;
  fecha: string;
  casos: number;
}

export const INDECOPI_SAMPLE: IndecopiSample[] = [
  { expediente: 'EXP-2026-0481', categoria: 'Cobros indebidos', institucion: 'Banco Nuevo Horizonte del Perú', estado: 'En trámite', fecha: '2026-05-20', casos: 14 },
  { expediente: 'EXP-2026-0467', categoria: 'Operación no reconocida', institucion: 'Financiera Surandina del Perú', estado: 'En trámite', fecha: '2026-05-18', casos: 9 },
  { expediente: 'EXP-2026-0452', categoria: 'Métodos abusivos de cobranza', institucion: 'Cooperativa de Ahorro Coopac Andes Centro', estado: 'Apelación', fecha: '2026-05-15', casos: 6 },
  { expediente: 'EXP-2026-0440', categoria: 'Falta de información', institucion: 'Banco Nuevo Horizonte del Perú', estado: 'Resuelto', fecha: '2026-05-12', casos: 4 },
  { expediente: 'EXP-2026-0431', categoria: 'Publicidad engañosa', institucion: 'Financiera Surandina del Perú', estado: 'En trámite', fecha: '2026-05-10', casos: 7 },
  { expediente: 'EXP-2026-0419', categoria: 'Demora en resolución', institucion: 'Cooperativa de Ahorro Coopac Andes Centro', estado: 'En trámite', fecha: '2026-05-08', casos: 5 },
  { expediente: 'EXP-2026-0405', categoria: 'Incumplimiento de contrato', institucion: 'Banco Nuevo Horizonte del Perú', estado: 'Resuelto', fecha: '2026-05-05', casos: 3 },
  { expediente: 'EXP-2026-0392', categoria: 'Cobros indebidos', institucion: 'Financiera Surandina del Perú', estado: 'Apelación', fecha: '2026-05-03', casos: 8 },
  { expediente: 'EXP-2026-0381', categoria: 'Operación no reconocida', institucion: 'Banco Nuevo Horizonte del Perú', estado: 'En trámite', fecha: '2026-04-29', casos: 11 },
  { expediente: 'EXP-2026-0370', categoria: 'Calidad de servicio', institucion: 'Cooperativa de Ahorro Coopac Andes Centro', estado: 'Resuelto', fecha: '2026-04-26', casos: 2 },
  { expediente: 'EXP-2026-0358', categoria: 'Falta de información', institucion: 'Financiera Surandina del Perú', estado: 'En trámite', fecha: '2026-04-22', casos: 5 },
];

export interface DscSample {
  fecha: string;
  canal: string;
  tema: string;
  consultas: number;
  estado: string;
}

export const DSC_SAMPLE: DscSample[] = [
  { fecha: '2026-05-28', canal: 'Presencial', tema: 'Demora en atención de reclamo', consultas: 22, estado: 'En seguimiento' },
  { fecha: '2026-05-28', canal: 'Telefónico', tema: 'Información sobre comisiones', consultas: 17, estado: 'Atendido' },
  { fecha: '2026-05-27', canal: 'Web', tema: 'Suplantación / fraude', consultas: 11, estado: 'Derivado a conducta' },
  { fecha: '2026-05-27', canal: 'App', tema: 'Cobros no reconocidos', consultas: 9, estado: 'En seguimiento' },
  { fecha: '2026-05-26', canal: 'Presencial', tema: 'Acceso a productos', consultas: 7, estado: 'Atendido' },
  { fecha: '2026-05-26', canal: 'Telefónico', tema: 'Reversión de cargo', consultas: 6, estado: 'En seguimiento' },
  { fecha: '2026-05-25', canal: 'Web', tema: 'Tasa de interés del crédito', consultas: 5, estado: 'Atendido' },
  { fecha: '2026-05-25', canal: 'App', tema: 'Bloqueo de tarjeta', consultas: 5, estado: 'Atendido' },
  { fecha: '2026-05-24', canal: 'Presencial', tema: 'Estado de cuenta erróneo', consultas: 4, estado: 'En seguimiento' },
  { fecha: '2026-05-24', canal: 'Telefónico', tema: 'Publicidad de promociones', consultas: 3, estado: 'Atendido' },
  { fecha: '2026-05-23', canal: 'Web', tema: 'Cancelación de producto', consultas: 3, estado: 'Derivado a conducta' },
  { fecha: '2026-05-23', canal: 'App', tema: 'Demora en desembolso', consultas: 2, estado: 'En seguimiento' },
];

export const FRAUD_LABEL_ES: Record<string, string> = {
  PHISHING_KEYWORD: 'Phishing',
  SCAM_KEYWORD: 'Estafa',
  FAKE_APP_KEYWORD: 'Aplicación falsa',
  FAKE_AGENT_KEYWORD: 'Agente falso',
  UNAUTHORIZED_FEE_KEYWORD: 'Cargo no autorizado',
  UNAUTHORIZED_CHARGE_KEYWORD: 'Consumo no autorizado',
};
