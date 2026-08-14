import React from 'react';

interface HeroProps {
  onLaunch: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onLaunch }) => {
  return (
    <section id="home" className="pt-32 pb-40 px-6 max-w-5xl mx-auto flex flex-col items-center text-center">
      <span className="text-xs font-bold uppercase tracking-widest text-[#6b6b6b] mb-6">
        AI-native supply chain intelligence
      </span>
      
      <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-[#1a1a1a] mb-8 leading-tight">
        Turning supply chain data <br className="hidden md:block" /> into intelligent action.
      </h1>
      
      <p className="text-xl md:text-2xl text-[#6b6b6b] max-w-2xl mb-12 leading-relaxed">
        Continuously monitor operations, detect risks before they disrupt, and generate executive-ready action plans in real-time.
      </p>
      
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <button 
          onClick={onLaunch}
          className="bg-[#2563eb] hover:bg-blue-700 text-white px-8 py-4 rounded-full text-lg font-medium transition-colors shadow-sm w-full sm:w-auto"
        >
          Launch app
        </button>
        <a 
          href="#contact"
          className="text-[#1a1a1a] hover:text-[#6b6b6b] px-8 py-4 font-medium transition-colors w-full sm:w-auto"
        >
          Contact us
        </a>
      </div>
    </section>
  );
};
