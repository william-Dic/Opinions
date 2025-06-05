import React, { useState } from 'react';
import './App.css';

function App() {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess(false); // Reset success state on new submission
    setIsLoading(true);

    const phoneRegex = /^\+?[1-9]\d{1,14}$/;
    if (!phoneRegex.test(phoneNumber.replace(/\D/g, ''))) {
      setError('Please enter a valid phone number (e.g., +1234567890)');
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch('http://localhost:5000/request_call', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ phone_number: phoneNumber }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to request call. Please check the server.' }));
        throw new Error(errorData.message || 'Failed to request call');
      }

      setSuccess(true);
      // Optionally clear phone number after success
      // setPhoneNumber(''); 
    } catch (err) {
      setError(err.message || 'Failed to request call. Please try again later.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <nav className="navbar">
        <div className="navbar-logo">Opinions</div>
        {/* Future auth buttons can go here */}
      </nav>

      <main className="hero-container">
        <div className="content">
          <h1>
            Get Expert Feedback <span className="highlight">on Your Startup Idea</span>
          </h1>
          <p className="subtitle">
            Our AI agents will call you to discuss your startup idea and provide valuable insights.
          </p>

          {!success ? (
            <form onSubmit={handleSubmit} className="phone-form">
              <div className="input-group">
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="Enter your phone number (e.g. +14155552671)"
                  className="phone-input"
                  disabled={isLoading}
                  aria-label="Phone number"
                />
                <button 
                  type="submit" 
                  className="submit-button"
                  disabled={isLoading}
                >
                  {isLoading ? 'Requesting Call...' : 'Get Expert Call'}
                </button>
              </div>
              {error && <p className="error">{error}</p>}
            </form>
          ) : (
            <div className="success-message">
              <h2>Thank You!</h2>
              <p>We'll call you shortly at {phoneNumber}.</p>
              <p>Please keep your phone nearby.</p>
            </div>
          )}

          <div className="features">
            <div className="feature">
              <h3>Market Analysis</h3>
              <p>Understand market demand, target users, and viability.</p>
            </div>
            <div className="feature">
              <h3>Product Strategy</h3>
              <p>Refine product functionality, innovation, and technical feasibility.</p>
            </div>
            <div className="feature">
              <h3>Business Model</h3>
              <p>Evaluate revenue models, cost structures, and growth paths.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
