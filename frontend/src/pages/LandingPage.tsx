import React from 'react';
import { Navbar } from '../components/landing/Navbar';
import { Hero } from '../components/landing/Hero';
import { Product } from '../components/landing/Product';
import { About } from '../components/landing/About';
import { Contact } from '../components/landing/Contact';
import { Footer } from '../components/landing/Footer';

interface LandingPageProps {
  onLaunch: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onLaunch }) => {
  return (
    <div className="bg-[#f4f4f2] text-[#1a1a1a] min-h-screen font-sans selection:bg-[#2563eb] selection:text-white">
      <Navbar onLaunch={onLaunch} />
      <Hero onLaunch={onLaunch} />
      <Product />
      <About />
      <Contact />
      <Footer />
    </div>
  );
};
