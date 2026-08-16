import { useTranslation } from 'react-i18next'
import './KnowledgePageHero.css'

export default function KnowledgePageHero() {
  const { t } = useTranslation()

  return (
    <header className="knowledge-hero" aria-label={t('knowledge.title')}>
      <div className="knowledge-hero__copy">
        <span className="knowledge-hero__eyebrow">{t('knowledge.eyebrow')}</span>
        <div className="panel-title-row knowledge-hero__title-row">
          <h1 className="knowledge-hero__title">{t('knowledge.title')}</h1>
          <p className="panel-subtitle">{t('knowledge.subtitle')}</p>
        </div>
      </div>
      <div className="knowledge-hero__visual" aria-hidden>
        <img
          src="/filex-hero-visual.png"
          alt=""
          className="knowledge-hero__visual-img knowledge-hero__visual-img--light"
          width={560}
          height={300}
          decoding="async"
        />
        <img
          src="/filex-hero-visual-dark.png"
          alt=""
          className="knowledge-hero__visual-img knowledge-hero__visual-img--dark"
          width={2798}
          height={1498}
          decoding="async"
        />
      </div>
    </header>
  )
}
