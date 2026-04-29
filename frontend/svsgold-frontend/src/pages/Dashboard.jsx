import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { LogOut, Menu, X, FileText, Plus, Settings, Home, Search, Phone, Mail, AlertCircle, UserPlus, Loader, Save, DollarSign, Calculator, Eye, Download, Upload }
  from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import ApplicationForm from '../components/ApplicationForm'
import ApplicationsView from '../components/ApplicationsView'
import CreateAccountPage from '../components/CreateAccountPage'
import { applicationsAPI, accountsAPI, transactionsAPI, estimationsAPI } from '../api/api'
import { formatDate } from '../utils/validation'
import * as XLSX from "xlsx";

export default function Dashboard({ loginData, onLogout }) {

  const navigate = useNavigate()

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [currentPage, setCurrentPage] = useState('applications')

  /* ---- Customer Search State ---- */
  const [searchType, setSearchType] = useState('mobile')
  const [searchValue, setSearchValue] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [customerFound, setCustomerFound] = useState(null)
  const [customerMobile, setCustomerMobile] = useState('')
  const [showCreateAccount, setShowCreateAccount] = useState(false)
  const [customerMode, setCustomerMode] = useState('existing')

  /* ---- Applications State ---- */
  const [applications, setApplications] = useState([])
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [branchFilter, setBranchFilter] = useState('')
  const [branches, setBranches] = useState([])

  /* ---- Collapsible & View State ---- */
  const [expandedSections, setExpandedSections] = useState({
    search: true,
    applications: true
  })
  const [viewMode, setViewMode] = useState('flat') // 'flat' or 'grouped'
  const [customerData, setCustomerData] = useState(null)

  // Fetch branches from API
  useEffect(() => {
    (async () => {
      try {
        const res = await applicationsAPI.getBranches()
        const b = res.data?.branches || []
        if (b.length > 0) setBranches(b)
      } catch {}
    })()
  }, [])

  /* ---- A key we bump to force ApplicationsView to re-mount & re-fetch ---- */
  const [refreshKey, setRefreshKey] = useState(0)

  /* ================================================================ */
  /*  FETCH APPLICATIONS                                              */
  /* ================================================================ */
  const fetchApplications = useCallback(async (mobile) => {
    if (!mobile) return
    try {
      setLoading(true)
      setError('')
      const response = await applicationsAPI.getApplicationsByUser(mobile)
      if (!response?.data?.applications) {
        setApplications([])
      } else {
        setApplications(response.data.applications)
      }
    } catch (err) {
      if (err.response?.status === 404) {
        setApplications([])
      } else {
        setError('Failed to load applications')
        setApplications([])
      }
    } finally {
      setLoading(false)
    }
  }, [])

  /* ================================================================ */
  /*  CUSTOMER SEARCH                                                 */
  /* ================================================================ */
  const handleSearchCustomerForProfile = async (e) => {
    e.preventDefault()
    setSearchError('')
    setCustomerFound(null)
    setApplications([])
    setError('')

    if (!searchValue.trim()) {
      setSearchError('Please enter a mobile number or email')
      return
    }

    if (searchType === 'mobile' && !/^[0-9]{10}$/.test(searchValue.trim())) {
      setSearchError('Please enter a valid 10-digit mobile number')
      return
    }

    setSearching(true)
    try {
      const payload = searchType === 'mobile'
        ? { mobile: searchValue.trim() }
        : { email: searchValue.trim() }

      const response = await accountsAPI.checkAccount(payload)

      if (response.data.exists) {
        const mobile = searchType === 'mobile' ? searchValue.trim() : (response.data.mobile || searchValue.trim())
        activateCustomerInProfile(mobile)
      } else {
        setCustomerFound(false)
      }
    } catch (err) {
      console.error('Error searching customer:', err)
      setCustomerFound(false)
    } finally {
      setSearching(false)
    }
  }

  /* ---- Applications search handler ---- */
  const handleSearchCustomer = async (e) => {
    e.preventDefault()
    setSearchError('')
    setCustomerFound(null)
    setApplications([])
    setError('')

    if (!searchValue.trim()) {
      setSearchError('Please enter a mobile number or email')
      return
    }

    if (searchType === 'mobile' && !/^[0-9]{10}$/.test(searchValue.trim())) {
      setSearchError('Please enter a valid 10-digit mobile number')
      return
    }

    setSearching(true)
    try {
      const payload = searchType === 'mobile'
        ? { mobile: searchValue.trim() }
        : { email: searchValue.trim() }

      const response = await accountsAPI.checkAccount(payload)

      if (response.data.exists) {
        const mobile = searchType === 'mobile' ? searchValue.trim() : (response.data.mobile || searchValue.trim())
        activateCustomer(mobile)
      } else {
        setCustomerFound(false)
      }
    } catch (err) {
      console.error('Error searching customer:', err)
      setCustomerFound(false)
    } finally {
      setSearching(false)
    }
  }

  /* ---- Helper: set a customer as active and fetch their apps ---- */
  const activateCustomer = useCallback((mobile, page = 'applications') => {
    setCustomerFound(true)
    setCustomerMobile(mobile)
    setShowCreateAccount(false)
    setShowCreateForm(false)
    setCurrentPage(page)
    localStorage.setItem('svs_gold_login_data', JSON.stringify({
      ...loginData,
      mobile,
      accountExists: true
    }))
    // Bump refresh key so ApplicationsView re-mounts with fresh data
    setRefreshKey(prev => prev + 1)
    // Fetch customer details for display
    fetchCustomerDetails(mobile)
    fetchApplications(mobile)
  }, [loginData, fetchApplications])

  const activateCustomerInProfile = useCallback((mobile) => {
    activateCustomer(mobile, 'profile')
  }, [activateCustomer])

  /* ---- Fetch Customer Details ---- */
  const fetchCustomerDetails = useCallback(async (mobile) => {
    try {
      const response = await accountsAPI.searchCustomerSummary(mobile, 'customer')
      const account = response.data?.customer || response.data?.account || response.data || {}
      setCustomerData(account)
    } catch (err) {
      console.error('Error fetching customer summary:', err)
      try {
        const response = await accountsAPI.checkAccount({ mobile })
        const account = response.data?.account || response.data || {}
        setCustomerData(account)
      } catch (fallbackErr) {
        console.error('Fallback checkAccount failed:', fallbackErr)
      }
    }
  }, [])

  /* ---- Toggle Section Expansion ---- */
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  /* ================================================================ */
  /*  HANDLERS                                                        */
  /* ================================================================ */
  const handleClearCustomer = () => {
    setCustomerFound(null)
    setCustomerMobile('')
    setSearchValue('')
    setApplications([])
    setShowCreateForm(false)
    setShowCreateAccount(false)
    setError('')
    setSearchError('')
    setBranchFilter('')
    setCustomerData(null)
    localStorage.removeItem('user_mobile')
  }

  const handleGoHome = () => {
    setCurrentPage('applications')
    handleClearCustomer()
    navigate('/dashboard')
  }

  const handleCreateAccountForCustomer = () => {
    setCustomerMode('new')
    setShowCreateAccount(true)
  }

  const handleSelectExistingCustomer = () => {
    setCustomerMode('existing')
    setShowCreateAccount(false)
    setCurrentPage('applications')
    setExpandedSections(prev => ({ ...prev, search: true }))
  }

  const handleCreateAccountSuccess = (createdAccount = {}) => {
    const mobile = createdAccount?.mobile || createdAccount?.data?.mobile || customerMobile || searchValue.trim()
    if (!mobile) {
      console.warn('Unable to activate new customer: missing mobile')
      return
    }
    activateCustomer(mobile)
  }

  const handleApplicationSuccess = (newApplication) => {
    // Application was just created; close form and update local state immediately
    setShowCreateForm(false)
    setApplications(prev => {
      const exists = prev.some(app => app.application_no === newApplication.application_no)
      if (exists) {
        return prev.map(app => app.application_no === newApplication.application_no ? { ...app, ...newApplication } : app)
      }
      return [...prev, newApplication]
    })
    setRefreshKey(prev => prev + 1)
    fetchApplications(customerMobile)
  }

  /* ================================================================ */
  /*  MENU                                                            */
  /* ================================================================ */
  const menuItems = [
    { id: 'applications', label: 'Applications', icon: FileText, color: 'text-amber-700' },
    ...(customerFound ? [{ id: 'estimations', label: 'Estimations', icon: Calculator, color: 'text-amber-700' }] : []),
    { id: 'transactions', label: 'Transactions', icon: DollarSign, color: 'text-amber-700' },
    { id: 'profile', label: 'Profile', icon: Settings, color: 'text-amber-700' }
  ]

  /* ================================================================ */
  /*  CREATE ACCOUNT VIEW                                             */
  /* ================================================================ */
  if (showCreateAccount) {
    const fakeLoginData = {
      mobile: customerMobile || (searchType === 'mobile' ? searchValue.trim() : ''),
      email: searchType === 'email' ? searchValue.trim() : ''
    }
    return (
      <CreateAccountPage
        loginData={fakeLoginData}
        onBackToLogin={() => setShowCreateAccount(false)}
        onSuccess={handleCreateAccountSuccess}
      />
    )
  }

  /* ================================================================ */
  /*  RENDER                                                          */
  /* ================================================================ */
  return (
    <div className="flex h-screen" style={{ background: 'linear-gradient(135deg, #fdf8f0, #f9edda, #fdf8f0)' }}>

      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? 'w-64' : 'w-20'}
        text-white transition-all duration-300 shadow-2xl overflow-hidden`}
        style={{ background: 'linear-gradient(180deg, #a36e24, #8b5c1c)' }}
      >
        <div className="h-full flex flex-col">

          {/* Logo */}
          <div className="p-4 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(255,255,255,0.15)' }}>
            <div className={`flex items-center gap-3 ${!sidebarOpen && 'justify-center w-full'}`}>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center overflow-hidden shadow-md" style={{ background: 'rgba(255,255,255,0.18)' }}>
                <img src={import.meta.env.BASE_URL + 'svslogo-white.png'} alt="SVS Gold" className="w-10 h-10 object-contain" />
              </div>
              {sidebarOpen && <span className="font-bold text-xl tracking-wide">SVS Gold</span>}
            </div>
          </div>

          {/* Menu */}
          <nav className="flex-1 p-4 space-y-2">
            {menuItems.map(item => {
              const Icon = item.icon
              return (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => {
                    setCurrentPage(item.id)
                    setShowCreateAccount(false)
                  }}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200
                  ${currentPage === item.id ? 'shadow-lg' : 'hover:bg-white/10'}`}
                  style={currentPage === item.id ? { background: 'rgba(255,255,255,0.2)' } : {}}
                >
                  <Icon size={20} className="text-amber-200" />
                  {sidebarOpen && <span className="font-medium">{item.label}</span>}
                </button>
              )
            })}
          </nav>

          {/* Toggle */}
          <div className="p-4" style={{ borderTop: '1px solid rgba(255,255,255,0.15)' }}>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg hover:bg-white/10 transition-all duration-200"
            >
              {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
              {sidebarOpen && <span className="text-sm">Collapse</span>}
            </button>
          </div>

        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top Bar */}
        <header className="bg-white shadow-md px-8 py-5 flex items-center justify-between border-b border-gray-200">
          <div>
            <h1 className="text-3xl font-bold" style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              SVS Gold CRM
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              Logged in as: <span className="font-medium text-gray-700">{loginData.username || 'Admin'}</span>
              {customerMobile && (
                <span className="ml-3 text-amber-700 font-medium">• Customer: {customerMobile}</span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-4">
            <button onClick={handleGoHome} className="p-3 rounded-lg hover:bg-gray-100 transition-colors">
              <Home size={20} className="text-gray-600" />
            </button>
            <button
              onClick={onLogout}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors font-medium"
            >
              <LogOut size={18} />
              Logout
            </button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-8">
          {currentPage === 'applications' && (
            <div className="space-y-6">

              {/* ============================================================ */}
              {/*  CUSTOMER SEARCH PANEL WITH COLLAPSIBLE HEADER             */}
              {/* ============================================================ */}
              {!customerFound && !showCreateForm && (
                <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
                  {/* Collapsible Header */}
                  <div 
                    onClick={() => toggleSection('search')}
                    className="p-6 cursor-pointer hover:bg-gray-50 transition-colors flex items-center justify-between border-b"
                  >
                    <div>
                      <h2 className="text-2xl font-bold text-gray-900">🔍 Search Customer</h2>
                      <p className="text-gray-500 text-sm mt-1">Enter customer's mobile number or email to load their applications</p>
                    </div>
                    <div className="text-2xl">
                      {expandedSections.search ? '−' : '+'}
                    </div>
                  </div>

                  {/* Collapsible Content */}
                  {expandedSections.search && (
                    <div className="p-8">
                      {/* Customer Type Selector */}
                      <div className="flex flex-col md:flex-row gap-3 mb-6">
                        <button
                          type="button"
                          onClick={handleSelectExistingCustomer}
                          className={`flex-1 flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold transition-all duration-300 ${
                            customerMode === 'existing' ? 'text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          }`}
                          style={customerMode === 'existing' ? { background: 'linear-gradient(135deg, #c9943a, #a36e24)' } : {}}
                        >
                          <FileText size={18} />
                          Existing Customer
                        </button>
                        <button
                          type="button"
                          onClick={handleCreateAccountForCustomer}
                          className={`flex-1 flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold transition-all duration-300 ${
                            customerMode === 'new' ? 'text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                          }`}
                          style={customerMode === 'new' ? { background: 'linear-gradient(135deg, #c9943a, #a36e24)' } : {}}
                        >
                          <UserPlus size={18} />
                          New Customer
                        </button>
                      </div>

                      {customerMode === 'existing' ? (
                        <>
                          <div className="flex gap-3 mb-6">
                            <button
                              type="button"
                              onClick={() => { setSearchType('mobile'); setSearchValue(''); setSearchError(''); setCustomerFound(null) }}
                              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold transition-all duration-300 ${
                                searchType === 'mobile' ? 'text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                              }`}
                              style={searchType === 'mobile' ? { background: 'linear-gradient(135deg, #c9943a, #a36e24)' } : {}}
                            >
                              <Phone size={18} />
                              Mobile
                            </button>
                            <button
                              type="button"
                              onClick={() => { setSearchType('email'); setSearchValue(''); setSearchError(''); setCustomerFound(null) }}
                              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold transition-all duration-300 ${
                                searchType === 'email' ? 'text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                              }`}
                              style={searchType === 'email' ? { background: 'linear-gradient(135deg, #c9943a, #a36e24)' } : {}}
                            >
                              <Mail size={18} />
                              Email
                            </button>
                          </div>

                          {/* Search Input */}
                          <form onSubmit={handleSearchCustomer} className="flex gap-4">
                            <div className="relative flex-1">
                              <div className="absolute left-4 top-1/2 -translate-y-1/2" style={{ color: '#a36e24' }}>
                                {searchType === 'mobile' ? <Phone size={20} /> : <Mail size={20} />}
                              </div>
                              <input
                                type={searchType === 'mobile' ? 'tel' : 'email'}
                                placeholder={searchType === 'mobile' ? 'Enter 10-digit mobile number' : 'Enter email address'}
                                value={searchValue}
                                onChange={(e) => { setSearchValue(e.target.value); setSearchError(''); setCustomerFound(null) }}
                                maxLength={searchType === 'mobile' ? 10 : undefined}
                                className="w-full pl-12 pr-4 py-4 bg-gradient-to-b from-white to-gray-50 border-2 border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none transition-all duration-300 shadow-sm hover:shadow-md"
                                onFocus={(e) => { e.target.style.borderColor = '#a36e24'; e.target.style.boxShadow = '0 0 0 4px rgba(163, 110, 36, 0.1)' }}
                                onBlur={(e) => { e.target.style.borderColor = '#e5e7eb'; e.target.style.boxShadow = '' }}
                              />
                            </div>
                            <button
                              type="submit"
                              disabled={searching || !searchValue.trim()}
                              className="px-8 py-4 text-white font-bold rounded-xl transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                              style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)', boxShadow: '0 4px 14px 0 rgba(163, 110, 36, 0.3)' }}
                            >
                              {searching ? <Loader size={20} className="animate-spin" /> : <Search size={20} />}
                              {searching ? 'Searching...' : 'Search'}
                            </button>
                          </form>
                        </>
                      ) : (
                        <div className="p-8 rounded-3xl bg-amber-50 border border-amber-200 text-center">
                          <h3 className="text-xl font-semibold text-gray-900 mb-3">Create a new customer account</h3>
                          <p className="text-gray-600 mb-6">Start filling in customer information and add documents later from the profile page.</p>
                          <button
                            type="button"
                            onClick={() => setShowCreateAccount(true)}
                            className="inline-flex items-center gap-2 px-8 py-4 text-white font-semibold rounded-xl transition-all"
                            style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)', boxShadow: '0 4px 14px 0 rgba(163, 110, 36, 0.3)' }}
                          >
                            <UserPlus size={18} /> Create New Customer
                          </button>
                        </div>
                      )}

                      {/* Search Error */}
                      {searchError && (
                        <div className="flex items-start gap-3 p-4 bg-red-50 border-2 border-red-200 rounded-xl mt-4">
                          <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
                          <span className="text-sm text-red-700">{searchError}</span>
                        </div>
                      )}

                      {/* Customer Not Found */}
                      {customerFound === false && (
                        <div className="mt-6 p-6 border-2 rounded-xl" style={{ background: 'linear-gradient(135deg, #fdf8f0, #f9edda)', borderColor: '#e4b96e' }}>
                          <div className="flex items-start gap-3 mb-4">
                            <AlertCircle size={20} style={{ color: '#a36e24' }} className="flex-shrink-0 mt-0.5" />
                            <div>
                              <p className="text-sm font-medium" style={{ color: '#6e4816' }}>
                                No account found for this {searchType === 'mobile' ? 'mobile number' : 'email'}.
                              </p>
                              <p className="text-xs mt-1" style={{ color: '#8b5c1c' }}>
                                Would you like to create a new customer account?
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={handleCreateAccountForCustomer}
                            className="flex items-center gap-2 px-6 py-3 text-white font-semibold rounded-xl transition-all"
                            style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)', boxShadow: '0 4px 14px 0 rgba(163, 110, 36, 0.3)' }}
                          >
                            <UserPlus size={18} />
                            Create New Account
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ============================================================ */}
              {/*  CUSTOMER FOUND — Show applications                          */}
              {/* ============================================================ */}
              {customerFound === true && (
                <>
                  {/* Enhanced Customer Details Card */}
                  <div className="bg-gradient-to-r from-amber-50 to-amber-100 rounded-2xl shadow-lg p-6 border-l-4" style={{ borderLeftColor: '#a36e24' }}>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                      <div className="bg-white rounded-xl p-4 shadow-sm">
                        <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Name</p>
                        <p className="text-lg font-bold text-gray-900">
                          {customerData?.name || [customerData?.first_name, customerData?.last_name].filter(Boolean).join(' ') || '—'}
                        </p>
                      </div>

                      <div className="bg-white rounded-xl p-4 shadow-sm border-2 border-green-200">
                        <p className="text-xs font-semibold text-gray-500 uppercase mb-2">📞 Phone Number</p>
                        <p className="text-lg font-bold text-green-700 font-mono">{customerData?.phone || customerMobile || '—'}</p>
                      </div>

                      <div className="flex items-center justify-end">
                        <button
                          onClick={handleClearCustomer}
                          className="px-6 py-2 text-sm font-medium text-gray-600 bg-white hover:bg-gray-100 rounded-lg transition-colors border border-gray-200"
                        >
                          Change Customer
                        </button>
                      </div>
                    </div>
                  </div>

                  {showCreateForm && (
                    <ApplicationForm
                      userIdentifier={customerMobile}
                      onSuccess={handleApplicationSuccess}
                      onCancel={() => setShowCreateForm(false)}
                    />
                  )}

                  {!showCreateForm && (
                    <>
                      {/* Branch Filter Section */}
                      <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                          <div>
                            <label className="text-sm font-semibold text-gray-600 block mb-2">Filter by Branch</label>
                            <select
                              value={branchFilter}
                              onChange={(e) => setBranchFilter(e.target.value)}
                              className="w-full px-4 py-3 bg-white border-2 border-gray-200 rounded-xl text-gray-800 text-sm focus:outline-none focus:border-amber-500 transition-all"
                            >
                              <option value="">All Branches</option>
                              {(() => {
                                const appBranches = [...new Set(applications.map(a => a.place).filter(Boolean))]
                                const apiBranches = branches.map(b => b.branch_name)
                                const allNames = [...new Set([...appBranches, ...apiBranches])]
                                return allNames.map(name => <option key={name} value={name}>{name}</option>)
                              })()}
                            </select>
                          </div>

                          <div className="md:col-span-2 flex flex-col md:flex-row md:justify-end md:items-center gap-3">
                            {branchFilter && (
                              <button
                                onClick={() => setBranchFilter('')}
                                className="text-xs text-amber-700 hover:text-amber-800 font-medium underline"
                              >
                                Clear Branch Filter
                              </button>
                            )}

                            <button
                              onClick={() => setShowCreateForm(true)}
                              className="flex items-center justify-center gap-2 px-6 py-3 text-white rounded-xl shadow-md hover:shadow-lg transition-all bg-gradient-to-r from-amber-500 to-amber-700"
                            >
                              <Plus size={18} />
                              Create Application
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Loading */}
                      {loading && (
                        <div className="text-center py-20">
                          <div className="w-10 h-10 border-4 border-t-4 rounded-full animate-spin mx-auto mb-4" style={{ borderColor: '#f0d5a8', borderTopColor: '#a36e24' }}></div>
                          <p className="text-gray-600">Loading applications...</p>
                        </div>
                      )}

                      {/* Error */}
                      {!loading && error && (
                        <div className="bg-red-50 border-2 border-red-200 rounded-2xl p-8 text-center">
                          <h3 className="text-lg font-semibold text-red-700 mb-2">Failed to Load Applications</h3>
                          <p className="text-red-600">{error}</p>
                        </div>
                      )}

                      {/* Empty State */}
                      {!loading && !error && (() => {
                        const filtered = branchFilter
                          ? applications.filter(a => a.place === branchFilter)
                          : applications
                        return filtered.length === 0 ? (
                          <div className="bg-white rounded-2xl shadow-lg p-12 text-center">
                            <FileText size={60} className="mx-auto mb-6" style={{ color: '#c9943a' }} />
                            <h2 className="text-2xl font-bold text-gray-800 mb-4">
                              {branchFilter ? `No Applications for ${branchFilter}` : 'No Existing Applications Found'}
                            </h2>
                            <p className="text-gray-600">
                              {branchFilter ? 'Try selecting a different branch or clear the filter.' : "This customer doesn't have any existing applications yet."}
                            </p>
                          </div>
                        ) : (
                          <div>
                            <h3 className="text-lg font-bold text-gray-800 mb-4">
                              📊 Applications ({viewMode === 'flat' ? 'Flat View' : 'Grouped View'})
                            </h3>
                            <ApplicationsView
                              key={`${refreshKey}-${branchFilter}`}
                              userIdentifier={customerMobile}
                              applications={filtered}
                              loading={loading}
                              error={error}
                              onApplicationsUpdate={setApplications}
                            />
                          </div>
                        )
                      })()}
                    </>
                  )}
                </>
              )}

            </div>
          )}

          {currentPage === 'profile' && (
            <ProfileSection
              customerMobile={customerMobile}
              loginData={loginData}
              onAddCustomer={handleCreateAccountForCustomer}
              onSelectExistingCustomer={handleSelectExistingCustomer}
              onSearchCustomerForProfile={handleSearchCustomerForProfile}
              searchType={searchType}
              setSearchType={setSearchType}
              searchValue={searchValue}
              setSearchValue={setSearchValue}
              searching={searching}
              searchError={searchError}
              setCustomerFound={setCustomerFound}
              setShowCreateAccount={setShowCreateAccount}
            />
          )}

          {currentPage === 'transactions' && (
            <TransactionsSection customerMobile={customerMobile} />
          )}

          {currentPage === 'estimations' && customerFound && (
            <EstimationsSection customerMobile={customerMobile} />
          )}
        </main>
      </div>
    </div>
  )
}

const normalizeDateFieldValue = (value) => {
  if (!value) return ''
  if (typeof value === 'string') {
    const isoMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    if (isoMatch) return value
    const dmyMatch = value.match(/^(\d{2})-(\d{2})-(\d{4})$/)
    if (dmyMatch) return `${dmyMatch[3]}-${dmyMatch[2]}-${dmyMatch[1]}`
    const parsed = new Date(value)
    if (!isNaN(parsed)) return parsed.toISOString().slice(0, 10)
    return ''
  }
  if (value instanceof Date && !isNaN(value)) {
    return value.toISOString().slice(0, 10)
  }
  return ''
}

const ProfileField = React.memo(function ProfileField({ label, field, type, value, disabled, onChange, ic, rc, lc }) {
  const displayValue = React.useMemo(
    () => (type === 'date' && value ? formatDate(value) : (value != null ? String(value) : '—')),
    [type, value]
  )

  const fieldValue = React.useMemo(
    () => (type === 'date' ? normalizeDateFieldValue(value) : (value != null ? String(value) : '')),
    [type, value]
  )

  const handleInputChange = React.useCallback(
    (e) => onChange(field, e.target.value),
    [field, onChange]
  )

  return (
    <div>
      <label className={lc}>{label}</label>
      {disabled ? (
        <div className={rc}>{displayValue}</div>
      ) : (
        <input
          type={type || 'text'}
          value={fieldValue}
          onChange={handleInputChange}
          className={ic}
        />
      )}
    </div>
  )
})

/* ================================================================ */
/*  PROFILE SECTION — View & Edit Account Details                   */
/* ================================================================ */
function ProfileSection({ customerMobile, loginData, onAddCustomer, onSelectExistingCustomer, onSearchCustomerForProfile, searchType, setSearchType, searchValue, setSearchValue, searching, searchError, setCustomerFound, setShowCreateAccount }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({})
  const [editAddresses, setEditAddresses] = useState([])
  const [editBanks, setEditBanks] = useState([])
  const [editDocs, setEditDocs] = useState([])
  const [deletedDocumentIds, setDeletedDocumentIds] = useState([])
  const [showSearchForm, setShowSearchForm] = useState(false)

  const isAdmin = loginData?.username === 'admin' || loginData?.isAdmin

  const loadData = async () => {
    setLoading(true); setError('')
    try {
      // Use summary API for profile data: customer, addresses, bank_accounts, documents
      const res = await accountsAPI.searchCustomerSummary(customerMobile, "customer,addresses,bank_accounts,documents")
      const d = res.data || {}
      setData(d)
      setForm({ ...(d.customer || {}) })
      setEditAddresses(JSON.parse(JSON.stringify(d.addresses || [])))
      setEditBanks(JSON.parse(JSON.stringify(d.bank_accounts || [])))
      setEditDocs(JSON.parse(JSON.stringify(d.documents || [])))
      setDeletedDocumentIds([])
    } catch {
      try {
        const res2 = await accountsAPI.checkAccount({ mobile: customerMobile })
        const acc = res2.data?.account || res2.data || {}
        setData({ customer: acc, addresses: [], bank_accounts: [], documents: [] })
        setForm({ ...acc })
        setEditAddresses([]); setEditBanks([]); setEditDocs([])
      } catch { setError('Could not load account details') }
    } finally { setLoading(false) }
  }

  useEffect(() => { if (customerMobile) loadData() }, [customerMobile])

  const handleChange = React.useCallback((f, v) => {
    setForm(p => ({ ...p, [f]: v }))
    setSuccess('')
  }, [])

  const handleAddrChange = (i, f, v) => { setEditAddresses(prev => { const u = [...prev]; u[i] = { ...u[i], [f]: v }; return u }) }
  const handleBankChange = (i, f, v) => { setEditBanks(prev => { const u = [...prev]; u[i] = { ...u[i], [f]: v }; return u }) }
  const handleDocChange = (i, f, v) => {
    setEditDocs(prev => {
      const u = [...prev]
      u[i] = { ...u[i], [f]: v }
      return u
    })
  }
  const handleDocUpload = (index, file) => {
    if (!file) return
    if (file.size > 5 * 1024 * 1024) { setError('File size must be less than 5MB'); return }
    const reader = new FileReader()
    reader.onload = (e) => {
      setEditDocs(prev => {
        const u = [...prev]
        u[index] = { ...u[index], file_path: e.target.result, file_name: file.name, file_size_mb: (file.size / (1024 * 1024)).toFixed(2), _newFile: true }
        return u
      })
    }
    reader.readAsDataURL(file)
  }
  const handleDocRemove = (index) => {
    setEditDocs(prev => {
      const u = [...prev]
      u[index] = { ...u[index], file_path: '', file_name: '', file_size_mb: 0, _newFile: false }
      return u
    })
  }
  const handleDocDelete = (index) => {
    setEditDocs(prev => {
      const u = [...prev]
      const docToDelete = u[index]
      if (docToDelete?.document_id) {
        setDeletedDocumentIds(ids => [...ids, docToDelete.document_id])
      }
      u.splice(index, 1)
      return u
    })
  }
  const handleAddDocument = () => {
    setEditDocs(prev => ([
      ...prev,
      { document_type: '', document_number: '', file_path: '', file_name: '', file_size_mb: 0, _newFile: false }
    ]))
  }
  const DOCUMENT_TYPES = ['Photo', 'Aadhar', 'PAN', 'Address Proof', 'Bank Details', 'Others']

  const handleSave = async () => {
    setSaving(true); setError(''); setSuccess('')
    try {
      // 1. Update account — ensure aadhar_no is string
      await accountsAPI.updateAccount({
        account_type: form.account_type || '', account_code: form.account_code || '',
        first_name: form.first_name || '', last_name: form.last_name || '',
        mobile: form.mobile || customerMobile, phone: form.phone || '',
        email: form.email || '', gender: form.gender || '',
        date_of_birth: form.date_of_birth || '',
        aadhar_no: String(form.aadhar_no || ''),
        occupation: form.occupation || '',
        pan_no: String(form.pan_no || ''),
        source: form.source || 'web', owner: form.owner || 'admin',
        state: form.state || '', district: form.district || '',
        city: form.city || '', pincode: form.pincode || '',
        address_text: form.address_text || ''
      })

      // 2. Re-save addresses (POST overwrites)
      for (const addr of editAddresses) {
        try {
          await accountsAPI.addAddress(customerMobile, {
            address_type: addr.address_type || '', address_line: addr.address_line || '',
            street: addr.street || '', city: addr.city || '',
            state: addr.state || '', country: addr.country || 'India',
            pincode: addr.pincode || ''
          })
        } catch (e) { console.log('Address save error:', e) }
      }

      // 3. Re-save bank accounts (POST overwrites)
      for (const bank of editBanks) {
        try {
          await accountsAPI.addBankAccount(customerMobile, {
            bank_name: bank.bank_name || '', branch: bank.branch || '',
            account_number: bank.account_number || '', ifsc_code: bank.ifsc_code || '',
            account_holder_name: bank.account_holder_name || '',
            account_holder_type: bank.account_holder_type || 'Self',
            is_primary: bank.is_primary || false
          })
        } catch (e) { console.log('Bank save error:', e) }
      }

      // 4. Delete removed documents first
      for (const documentId of deletedDocumentIds) {
        try {
          await accountsAPI.deleteDocument(customerMobile, documentId)
        } catch (e) {
          console.log('Document delete error:', e)
        }
      }

      // 5. Validate documents before saving
      const docsToSave = editDocs.filter(doc => {
        // Only save documents that have both document_type AND file_path
        return doc.document_type && doc.file_path && doc.file_name
      })

      if (docsToSave.length < editDocs.length) {
        // Some documents are incomplete (missing file or type)
        const incompleteCount = editDocs.length - docsToSave.length
        setError(`${incompleteCount} document(s) incomplete - please remove or upload files for all documents`)
        setSaving(false)
        return
      }

      // 5. Re-save all remaining documents (both new and updated)
      for (const doc of docsToSave) {
        try {
          await accountsAPI.addDocument(customerMobile, {
            document_type: doc.document_type || '',
            document_number: doc.document_number || '',
            file_path: doc.file_path || '',
            file_name: doc.file_name || '',
            file_size_mb: parseFloat(doc.file_size_mb) || 0
          })
        } catch (e) {
          setError(`Failed to save ${doc.document_type}: ${e.response?.data?.detail || e.message}`)
          setSaving(false)
          return
        }
      }

      setDeletedDocumentIds([])
      setEditing(false)
      setSuccess('All details updated successfully!')
      // Reload fresh data
      await loadData()
    } catch (err) { setError(err.response?.data?.message || 'Failed to update account') }
    finally { setSaving(false) }
  }

  const handleCancel = () => {
    setForm({ ...(data?.customer || {}) })
    setEditAddresses(JSON.parse(JSON.stringify(data?.addresses || [])))
    setEditBanks(JSON.parse(JSON.stringify(data?.bank_accounts || [])))
    setEditDocs(JSON.parse(JSON.stringify(data?.documents || [])))
    setEditing(false); setError('')
  }

  const ic = 'w-full px-4 py-3 bg-gradient-to-b from-white to-gray-50 border-2 border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:border-amber-600 focus:ring-4 focus:ring-amber-600/10 transition-all shadow-sm hover:shadow-md hover:border-gray-300'
  const rc = 'w-full px-4 py-3 bg-gray-50 border-2 border-gray-100 rounded-xl text-gray-700 font-medium'
  const lc = 'block text-xs font-semibold text-gray-500 mb-1.5 uppercase tracking-wide'

  if (!customerMobile) return (
    <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
      {showSearchForm ? (
        <>
          <Search size={48} className="mx-auto mb-4 text-amber-300" />
          <h2 className="text-xl font-bold text-gray-800 mb-2">Search Existing Customer</h2>
          <p className="text-gray-500 mb-6">Enter mobile number or email to find and open customer profile.</p>
          
          <form onSubmit={onSearchCustomerForProfile} className="max-w-md mx-auto space-y-4">
            <div className="flex gap-2">
              <select
                value={searchType}
                onChange={(e) => setSearchType(e.target.value)}
                className="px-3 py-3 border-2 border-gray-200 rounded-xl text-gray-700 focus:outline-none focus:border-amber-600"
              >
                <option value="mobile">Mobile</option>
                <option value="email">Email</option>
              </select>
              <input
                type={searchType === 'mobile' ? 'tel' : 'email'}
                placeholder={searchType === 'mobile' ? 'Enter 10-digit mobile' : 'Enter email address'}
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
                className="flex-1 px-4 py-3 border-2 border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:border-amber-600 focus:ring-4 focus:ring-amber-600/10"
                required
              />
            </div>
            
            {searchError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
                {searchError}
              </div>
            )}
            
            <div className="flex gap-3">
              <button
                type="submit"
                disabled={searching}
                className="flex-1 inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-white font-semibold disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)' }}
              >
                {searching ? <Loader size={18} className="animate-spin" /> : <Search size={18} />}
                {searching ? 'Searching...' : 'Search Customer'}
              </button>
              <button
                type="button"
                onClick={() => setShowSearchForm(false)}
                className="px-6 py-3 rounded-xl text-gray-600 font-semibold border border-gray-300 hover:bg-gray-50 transition-all"
              >
                Cancel
              </button>
            </div>
          </form>
        </>
      ) : (
        <>
          <Settings size={48} className="mx-auto mb-4 text-amber-300" />
          <h2 className="text-xl font-bold text-gray-800 mb-2">No Customer Selected</h2>
          <p className="text-gray-500 mb-2">Search existing customer or create new customer.</p>
          <p className="text-sm text-gray-400 mb-4">Use the buttons below to open an existing customer profile or start a new customer record.</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-6">
            <button
              type="button"
              onClick={() => setShowSearchForm(true)}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-amber-800 font-semibold border border-amber-200 bg-amber-50 hover:bg-amber-100 transition-all"
            >
              <Search size={18} /> Existing Customer
            </button>
            <button
              type="button"
              onClick={onAddCustomer}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-white font-semibold"
              style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)' }}
            >
              <Plus size={18} /> New Customer
            </button>
          </div>
        </>
      )}
    </div>
  )
  if (loading) return (
    <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
      <Loader size={36} className="animate-spin mx-auto mb-4 text-amber-600" />
      <p className="text-gray-600">Loading customer details...</p>
    </div>
  )

  const cust = data?.customer || {}
  const addresses = editing ? editAddresses : (data?.addresses || [])
  const banks = editing ? editBanks : (data?.bank_accounts || [])
  const docs = data?.documents || []
  const d = editing ? form : cust

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Customer Profile</h2>
          <p className="text-gray-500 text-sm mt-1">{cust.first_name} {cust.last_name} • {customerMobile}</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onSelectExistingCustomer}
            className="px-4 py-2 text-sm font-medium text-gray-600 bg-white hover:bg-gray-100 rounded-lg transition-colors border border-gray-200"
          >
            Change Customer
          </button>
          {isAdmin && !editing && (
            <button onClick={() => setEditing(true)} className="flex items-center gap-2 px-5 py-2.5 text-white font-semibold rounded-xl text-sm" style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)' }}>
              <Settings size={16} /> Edit Details
            </button>
          )}
        </div>
      </div>


      {success && <div className="p-4 bg-green-50 border-2 border-green-200 rounded-xl text-sm text-green-700 font-medium">{success}</div>}
      {error && <div className="p-4 bg-red-50 border-2 border-red-200 rounded-xl text-sm text-red-700 font-medium">{error}</div>}

      {/* Account Info */}
      <div className="bg-white rounded-2xl shadow-lg p-8 space-y-5">
        <h3 className="text-lg font-bold text-gray-800 pb-3 border-b border-gray-100">Account Information</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <ProfileField key="account_type" label="Account Type" field="account_type" value={d.account_type} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="account_code" label="Account Code" field="account_code" value={d.account_code} disabled onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="mobile" label="Mobile" field="mobile" value={d.mobile} disabled onChange={handleChange} ic={ic} rc={rc} lc={lc} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <ProfileField key="first_name" label="First Name" field="first_name" value={d.first_name} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="last_name" label="Last Name" field="last_name" value={d.last_name} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <ProfileField key="email" label="Email" field="email" value={d.email} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="gender" label="Gender" field="gender" value={d.gender} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="date_of_birth" label="Date of Birth" field="date_of_birth" type="date" value={d.date_of_birth} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <ProfileField key="aadhar_no" label="Aadhar No" field="aadhar_no" value={d.aadhar_no} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="pan_no" label="PAN No" field="pan_no" value={d.pan_no} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
          <ProfileField key="occupation" label="Occupation" field="occupation" value={d.occupation} onChange={handleChange} ic={ic} rc={rc} lc={lc} />
        </div>
      </div>

      {/* Addresses */}
      <div className="bg-white rounded-2xl shadow-lg p-8 space-y-5">
        <h3 className="text-lg font-bold text-gray-800 pb-3 border-b border-gray-100">Addresses ({addresses.length})</h3>
        {addresses.length === 0 ? <p className="text-gray-400 text-sm">No addresses on file.</p> : (
          <div className="space-y-4">
            {addresses.map((addr, i) => (
              <div key={addr.address_id || i} className={`p-5 rounded-xl border ${editing ? 'bg-white border-amber-200' : 'bg-gray-50 border-gray-100'}`}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">{addr.address_type}</span>
                </div>
                {editing ? (
                  <div className="space-y-3">
                    <div>
                      <label className={lc}>Address Line</label>
                      <input value={addr.address_line || ''} onChange={e => handleAddrChange(i, 'address_line', e.target.value)} className={ic} />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div><label className={lc}>Street</label><input value={addr.street || ''} onChange={e => handleAddrChange(i, 'street', e.target.value)} className={ic} /></div>
                      <div><label className={lc}>Pincode</label><input value={addr.pincode || ''} onChange={e => handleAddrChange(i, 'pincode', e.target.value)} className={ic} /></div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div><label className={lc}>City</label><input value={addr.city || ''} onChange={e => handleAddrChange(i, 'city', e.target.value)} className={ic} /></div>
                      <div><label className={lc}>State</label><input value={addr.state || ''} onChange={e => handleAddrChange(i, 'state', e.target.value)} className={ic} /></div>
                      <div><label className={lc}>Country</label><input value={addr.country || 'India'} disabled className={`${ic} opacity-60`} /></div>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="text-sm text-gray-800 font-medium">{addr.address_line || '—'}</p>
                    {addr.street && <p className="text-sm text-gray-600">{addr.street}</p>}
                    <p className="text-sm text-gray-600">{[addr.city, addr.state, addr.pincode].filter(Boolean).join(', ')}</p>
                    <p className="text-xs text-gray-400 mt-1">{addr.country || 'India'}</p>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bank Accounts */}
      <div className="bg-white rounded-2xl shadow-lg p-8 space-y-5">
        <h3 className="text-lg font-bold text-gray-800 pb-3 border-b border-gray-100">Bank Accounts ({banks.length})</h3>
        {banks.length === 0 ? <p className="text-gray-400 text-sm">No bank accounts on file.</p> : (
          <div className="space-y-4">
            {banks.map((bank, i) => (
              <div key={bank.bank_account_id || i} className={`p-5 rounded-xl border ${editing ? 'bg-white border-amber-200' : 'bg-gray-50 border-gray-100'}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-800">{editing ? '' : (bank.bank_name || '—')}</span>
                    {bank.is_primary && <span className="text-xs text-white px-2 py-0.5 rounded-full font-medium" style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)' }}>Primary</span>}
                  </div>
                </div>
                {editing ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div><label className={lc}>Bank Name</label><input value={bank.bank_name || ''} onChange={e => handleBankChange(i, 'bank_name', e.target.value)} className={ic} /></div>
                      <div><label className={lc}>Branch</label><input value={bank.branch || ''} onChange={e => handleBankChange(i, 'branch', e.target.value)} className={ic} /></div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div><label className={lc}>Account Number</label><input value={bank.account_number || ''} onChange={e => handleBankChange(i, 'account_number', e.target.value)} className={ic} /></div>
                      <div><label className={lc}>IFSC Code</label><input value={bank.ifsc_code || ''} onChange={e => handleBankChange(i, 'ifsc_code', e.target.value.toUpperCase())} className={ic} /></div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div><label className={lc}>Account Holder Name</label><input value={bank.account_holder_name || ''} onChange={e => handleBankChange(i, 'account_holder_name', e.target.value)} className={ic} /></div>
                      <div><label className={lc}>Holder Type</label>
                        <select value={bank.account_holder_type || 'Self'} onChange={e => handleBankChange(i, 'account_holder_type', e.target.value)} className={ic}>
                          {['Self','Spouse','Business Partner','Parent','Child','Other'].map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div><span className="text-xs text-gray-400 block">Account No</span><span className="font-medium text-gray-700">{bank.account_number || '—'}</span></div>
                    <div><span className="text-xs text-gray-400 block">IFSC</span><span className="font-medium text-gray-700">{bank.ifsc_code || '—'}</span></div>
                    <div><span className="text-xs text-gray-400 block">Branch</span><span className="font-medium text-gray-700">{bank.branch || '—'}</span></div>
                    <div><span className="text-xs text-gray-400 block">Holder</span><span className="font-medium text-gray-700">{bank.account_holder_name || '—'}</span></div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-lg p-8 space-y-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <h3 className="text-lg font-bold text-gray-800 pb-3 border-b border-gray-100 md:border-none">Documents ({editing ? editDocs.length : docs.length})</h3>
          {editing && (
            <button
              type="button"
              onClick={handleAddDocument}
              className="self-start md:self-auto inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white"
              style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)' }}
            >
              <Plus size={16} /> Add Document
            </button>
          )}
        </div>
        {(editing ? editDocs : docs).length === 0 ? <p className="text-gray-400 text-sm">No documents uploaded.</p> : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(editing ? editDocs : docs).map((doc, i) => {
              const hasFile = !!doc.file_name
              return (
                <div key={doc.document_id || `${doc.document_type || 'doc'}_${i}`} className={`p-5 rounded-xl border transition-all duration-200 ${hasFile ? 'border-green-200 bg-green-50/50' : 'border-gray-200 bg-white/80 hover:border-amber-300 hover:shadow-md'}`}>
                  <div className="flex items-center justify-between gap-3 mb-3">
                    <div>
                      <h4 className="font-semibold text-gray-800 text-sm">{doc.document_type || 'Document'}</h4>
                      <p className="text-xs text-gray-500">{editing ? 'Upload or replace the file' : 'Uploaded document'}</p>
                    </div>
                    {editing && (
          <button
            type="button"
            onClick={() => doc.document_id ? handleDocDelete(i) : handleDocRemove(i)}
            className="text-xs font-medium text-red-600 hover:text-red-800"
          >
            {doc.document_id ? 'Delete' : 'Clear'}
          </button>
        )}
                  </div>

                  {editing ? (
                    <div className="space-y-3">
                      <div>
                        <label className={lc}>Document Type</label>
                        <select 
                          value={doc.document_type || ''} 
                          onChange={(e) => handleDocChange(i, 'document_type', e.target.value)}
                          className={ic}
                        >
                          <option value="">-- Select Document Type --</option>
                          {DOCUMENT_TYPES.map(type => <option key={type} value={type}>{type}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className={lc}>Document Number (optional)</label>
                        <input 
                          type="text" 
                          value={doc.document_number || ''} 
                          onChange={(e) => handleDocChange(i, 'document_number', e.target.value)}
                          placeholder="e.g., 12345678901234"
                          className={ic}
                        />
                      </div>
                      <div>
                        <label className={lc}>File</label>
                        <div className="flex flex-col gap-3">
                          <label htmlFor={`profile-doc-file-${i}`} className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-dashed border-amber-300 text-sm text-amber-700 cursor-pointer hover:bg-amber-50 transition-colors">
                            <Upload size={16} /> {hasFile ? 'Replace file' : 'Select file'}
                          </label>
                          <input
                            id={`profile-doc-file-${i}`}
                            type="file"
                            accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                            className="hidden"
                            onChange={(e) => handleDocUpload(i, e.target.files?.[0])}
                          />
                          {hasFile ? (
                            <div className="flex items-center justify-between gap-2 px-3 py-2 bg-white rounded-lg border border-green-200">
                              <div className="text-sm text-gray-700 truncate">{doc.file_name}</div>
                              <div className="text-xs text-gray-400">{doc.file_size_mb}MB</div>
                            </div>
                          ) : (
                            <p className="text-xs text-gray-500">Accepted: PDF, JPG, PNG, DOC, DOCX. Max 5MB.</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg border border-green-100">
                        <FileText size={14} className="text-green-600 flex-shrink-0" />
                        <span className="text-xs text-gray-700 truncate flex-1">{doc.file_name || 'Uploaded file'}</span>
                        <span className="text-xs text-gray-400 flex-shrink-0">{doc.file_size_mb ? `${doc.file_size_mb}MB` : ''}</span>
                      </div>
                      <div className="flex gap-2 mt-3">
                        <a
                          href={doc.file_path}
                          target="_blank"
                          rel="noreferrer"
                          className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-white text-amber-700 border border-amber-200 hover:bg-amber-50 transition-colors"
                        >
                          <Eye size={13} /> Preview
                        </a>
                        <a
                          href={doc.file_path}
                          download={doc.file_name || `${doc.document_type || 'document'}`}
                          className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-white text-green-700 border border-green-200 hover:bg-green-50 transition-colors"
                        >
                          <Download size={13} /> Download
                        </a>
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Edit Actions */}
      {editing && (
        <div className="flex justify-center gap-4">
          <button onClick={handleCancel} className="px-8 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-xl text-sm">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="px-10 py-2.5 text-white font-semibold rounded-xl shadow-lg disabled:opacity-50 flex items-center gap-2 text-sm" style={{ background: 'linear-gradient(135deg, #c9943a, #a36e24)' }}>
            {saving ? <><Loader size={16} className="animate-spin" /> Saving...</> : <><Save size={16} /> Save Changes</>}
          </button>
        </div>
      )}
    </div>
  )
}

/* ================================================================ */
/*  TRANSACTIONS SECTION — Admin-only, all users                    */
/* ================================================================ */
/* ================================================================ */
/*  TRANSACTIONS SECTION — Enhanced with customer details           */
/* ================================================================ */
function TransactionsSection({ customerMobile }) 
{

  const [data, setData] = useState({
    invoices: [],
    invoice_items: [],
  });

  const [filteredItems, setFilteredItems] = useState([]);

  const [mode, setMode] = useState("single");
  const [mobileInput, setMobileInput] = useState("");
  const [loading, setLoading] = useState(false);

  const [period, setPeriod] = useState("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const [sortOrder, setSortOrder] = useState("desc");

  const cur = (n) =>
    "₹" +
    Number(n || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
    });

  // ================= FILTER =================
  const applyFilters = (items, invoices, selectedPeriod = period) => {
    let result = [...items];

    if (selectedPeriod !== "all") {
      const days = parseInt(selectedPeriod);
      const cutoff = new Date();
      cutoff.setDate(new Date().getDate() - days);

      result = result.filter((item) => {
        const inv = invoices.find(
          (i) => i.payment_invoice_id === item.payment_invoice_id
        );
        return inv && new Date(inv.invoice_date) >= cutoff;
      });
    }

    if (fromDate && toDate) {
      result = result.filter((item) => {
        const inv = invoices.find(
          (i) => i.payment_invoice_id === item.payment_invoice_id
        );
        if (!inv) return false;

        const d = new Date(inv.invoice_date);
        return d >= new Date(fromDate) && d <= new Date(toDate);
      });
    }

    return result;
  };

  // ================= SORT =================
  const sortItems = (items, order) => {
    return [...items].sort((a, b) => {
      const valA = Number(a.gross_amount || 0);
      const valB = Number(b.gross_amount || 0);
      return order === "asc" ? valA - valB : valB - valA;
    });
  };

  // ================= LOAD =================
  const loadData = async () => {
    setLoading(true);

    const res =
      mode === "single"
        ? await transactionsAPI.getAll(mobileInput)
        : await transactionsAPI.getAll();

    setData(res.data);

    const filtered = applyFilters(
      res.data.invoice_items,
      res.data.invoices
    );

    setFilteredItems(sortItems(filtered, sortOrder));

    setLoading(false);
  };

  // ================= SUMMARY =================
  const summary = filteredItems.reduce(
    (acc, i) => {
      const gross = Number(i.gross_amount || 0);
      const net = Number(i.net_amount || 0);
      const exec = gross - net;

      acc.gross += gross;
      acc.net += net;
      acc.exec += exec;

      return acc;
    },
    { gross: 0, net: 0, exec: 0 }
  );

  // ================= EXPORT =================
  const exportExcel = () => {
    const rows = filteredItems.map((i) => {
      const inv = data.invoices.find(
        (inv) => inv.payment_invoice_id === i.payment_invoice_id
      );

      const exec = Number(i.gross_amount) - Number(i.net_amount);

      return {
        Invoice: inv?.invoice_no,
        Date: inv?.invoice_date,
        Customer: inv?.customer_name,
        Mobile: inv?.customer_details?.mobile,
        Item: i.item_name,
        WT_Before: i.weight_before_melting,
        WT_After: i.weight_after_melting,
        Purity: i.purity_after_melting,
        Rate: i.gold_rate_per_gm,
        Deduction: i.deduction_percentage,
        Gross: i.gross_amount,
        Net: i.net_amount,
        Executive_Charges: exec.toFixed(2),
      };
    });

    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Transactions");
    XLSX.writeFile(wb, "transactions.xlsx");
  };

  return (
    <div className="p-6 bg-[#F7F4EE] min-h-screen space-y-6">

      {/* MODE */}
      <div className="flex gap-3">
        <button
          onClick={() => setMode("single")}
          className={`px-4 py-2 rounded ${
            mode === "single" ? "bg-[#B68A2E] text-white" : "bg-gray-200"
          }`}
        >
          Single
        </button>

        <button
          onClick={() => {
            setMode("all");
            setMobileInput("");
          }}
          className={`px-4 py-2 rounded ${
            mode === "all" ? "bg-[#B68A2E] text-white" : "bg-gray-200"
          }`}
        >
          All
        </button>
      </div>

      {/* SEARCH */}
      <div className="bg-white p-4 rounded-xl shadow flex gap-3 items-center">
        {mode === "single" && (
          <input
            value={mobileInput}
            onChange={(e) => setMobileInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadData()}
            placeholder="Enter mobile"
            className="border px-3 py-2 rounded w-56"
          />
        )}

        <button
          onClick={loadData}
          className="bg-[#B68A2E] text-white px-5 py-2 rounded flex items-center gap-2"
        >
          {loading && (
            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          )}
          {loading ? "Loading..." : "Load"}
        </button>
      </div>

      {/* FILTER + SORT */}
      <div className="bg-white p-4 rounded-xl shadow space-y-3">

        <div className="flex gap-3 flex-wrap">
          {["7", "14", "30", "all"].map((p) => (
            <button
              key={p}
              onClick={() => {
                setPeriod(p);
                setFilteredItems(
                  sortItems(
                    applyFilters(data.invoice_items, data.invoices, p),
                    sortOrder
                  )
                );
              }}
              className={`px-3 py-1 rounded ${
                period === p ? "bg-[#B68A2E] text-white" : "bg-gray-200"
              }`}
            >
              {p === "all" ? "All" : `Last ${p}d`}
            </button>
          ))}

          <button
            onClick={() => {
              setSortOrder("asc");
              setFilteredItems(sortItems(filteredItems, "asc"));
            }}
            className="px-3 py-1 bg-gray-200 rounded"
          >
            ↑ Asc
          </button>

          <button
            onClick={() => {
              setSortOrder("desc");
              setFilteredItems(sortItems(filteredItems, "desc"));
            }}
            className="px-3 py-1 bg-gray-200 rounded"
          >
            ↓ Desc
          </button>
        </div>

        {/* CUSTOM DATE */}
        <div className="flex gap-3 items-center">
          <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="border px-2 py-1 rounded"/>
          <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="border px-2 py-1 rounded"/>

          <button
            onClick={() =>
              setFilteredItems(
                sortItems(
                  applyFilters(data.invoice_items, data.invoices),
                  sortOrder
                )
              )
            }
            className="bg-[#B68A2E] text-white px-3 py-1 rounded"
          >
            Apply
          </button>
        </div>
      </div>

      {/* EXPORT */}
      <button
        onClick={exportExcel}
        className="bg-green-600 text-white px-4 py-2 rounded"
      >
        Export Excel
      </button>

      {/* SUMMARY */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">

        <div className="bg-white p-4 rounded shadow">
          <p className="font-semibold text-gray-700">Items</p>
          <p className="text-2xl font-bold">{filteredItems.length}</p>
        </div>

        <div className="bg-white p-4 rounded shadow">
          <p className="font-semibold text-gray-700">💰 Gross</p>
          <p className="text-2xl font-bold text-[#B68A2E]">{cur(summary.gross)}</p>
        </div>

        <div className="bg-white p-4 rounded shadow">
          <p className="font-semibold text-gray-700">📊 Net</p>
          <p className="text-2xl font-bold text-[#B68A2E]">{cur(summary.net)}</p>
        </div>

        <div className="bg-white p-4 rounded shadow">
          <p className="font-semibold text-gray-700">⚙️ Executive Charges</p>
          <p className="text-2xl font-bold text-[#B68A2E]">{cur(summary.exec)}</p>
        </div>

      </div>

      {/* TABLE */}
      <div className="bg-white rounded-xl shadow overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-[#B68A2E] text-white">
            <tr>
              <th className="px-3 py-2">Invoice</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Customer</th>
              <th className="px-3 py-2">Mobile</th>
              <th className="px-3 py-2">Item</th>
              <th className="px-3 py-2">Wt Before</th>
              <th className="px-3 py-2">Wt After</th>
              <th className="px-3 py-2">Purity</th>
              <th className="px-3 py-2">Rate</th>
              <th className="px-3 py-2">Ded %</th>
              <th className="px-3 py-2">Gross</th>
              <th className="px-3 py-2">Net</th>
              <th className="px-3 py-2">Executive Charges</th>
            </tr>
          </thead>

          <tbody>
            {filteredItems.map((i) => {
              const inv = data.invoices.find(
                (inv) => inv.payment_invoice_id === i.payment_invoice_id
              );

              const exec =
                Number(i.gross_amount || 0) -
                Number(i.net_amount || 0);

              return (
                <tr key={i.invoice_item_id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2">{inv?.invoice_no}</td>
                  <td className="px-3 py-2">{inv?.invoice_date}</td>
                  <td className="px-3 py-2">{inv?.customer_name}</td>
                  <td className="px-3 py-2">{inv?.customer_details?.mobile}</td>
                  <td className="px-3 py-2">{i.item_name}</td>
                  <td className="px-3 py-2">{i.weight_before_melting}</td>
                  <td className="px-3 py-2">{i.weight_after_melting}</td>
                  <td className="px-3 py-2">{i.purity_after_melting}%</td>
                  <td className="px-3 py-2">{cur(i.gold_rate_per_gm)}</td>
                  <td className="px-3 py-2">{i.deduction_percentage}%</td>
                  <td className="px-3 py-2">{cur(i.gross_amount)}</td>
                  <td className="px-3 py-2">{cur(i.net_amount)}</td>
                  <td className="px-3 py-2">{cur(exec)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

    </div>
  );
}

/* ================================================================ */
/*  ESTIMATIONS SECTION — Shows all estimations for a customer      */
/* ================================================================ */
function EstimationsSection({ customerMobile }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    if (!customerMobile) return
    const load = async () => {
      setLoading(true); setError('')
      try {
        const res = await estimationsAPI.getByUser(customerMobile)
        setData(res.data)
      } catch (e) {
        setError('Failed to load estimations: ' + (e.message || 'Unknown error'))
      } finally { setLoading(false) }
    }
    load()
  }, [customerMobile])

  const cur = (n) => n != null ? '₹' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '₹0.00'

  if (!customerMobile) return (
    <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
      <Calculator size={48} className="mx-auto mb-4 text-amber-300" />
      <h2 className="text-xl font-bold text-gray-800 mb-2">No Customer Selected</h2>
      <p className="text-gray-500">Search for a customer to view their estimations.</p>
    </div>
  )

  if (loading) return (
    <div className="text-center py-20">
      <Loader size={36} className="animate-spin mx-auto mb-4 text-amber-600" />
      <p className="text-gray-600">Loading estimations...</p>
    </div>
  )

  const estimations = data?.estimations || []
  const totalAmount = estimations.reduce((s, e) => s + (parseFloat(e.total_net_amount) || 0), 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Estimations</h2>
          <p className="text-gray-500 text-sm mt-1">Customer: {customerMobile} — {estimations.length} estimation{estimations.length !== 1 ? 's' : ''} found</p>
        </div>
      </div>

      {error && <div className="p-4 bg-red-50 border-2 border-red-200 rounded-xl text-sm text-red-700">{error}</div>}

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl shadow-md p-6 border border-gray-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #f0d5a8, #e4b96e)' }}>
              <FileText size={20} style={{ color: '#6e4816' }} />
            </div>
            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Total Estimations</span>
          </div>
          <p className="text-3xl font-bold text-gray-900">{estimations.length}</p>
        </div>
        <div className="bg-white rounded-2xl shadow-md p-6 border border-gray-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #c5e1f5, #7ab5e0)' }}>
              <DollarSign size={20} className="text-blue-700" />
            </div>
            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Total Estimated Value</span>
          </div>
          <p className="text-3xl font-bold text-gray-900">{cur(totalAmount)}</p>
        </div>
      </div>

      {/* Estimations List */}
      {estimations.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-md p-8 text-center border border-gray-100">
          <Calculator size={48} className="mx-auto mb-4 text-amber-200" />
          <p className="text-gray-400">No estimations found for this customer.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {estimations.map((est) => {
            const isExpanded = expandedId === est.estimation_id
            const items = est.items || []
            return (
              <div key={est.estimation_id} className="bg-white rounded-2xl shadow-md border border-gray-100 overflow-hidden transition-all">
                {/* Estimation Header */}
                <button onClick={() => setExpandedId(isExpanded ? null : est.estimation_id)} className="w-full flex items-center justify-between p-6 hover:bg-amber-50/30 transition-colors text-left">
                  <div className="flex items-start gap-4 flex-1">
                    <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'linear-gradient(135deg, #f0d5a8, #e4b96e)' }}>
                      <Calculator size={22} style={{ color: '#6e4816' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 flex-wrap">
                        <h3 className="text-lg font-bold text-gray-900">{est.estimation_no}</h3>
                        <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                          est.status === 'ESTIMATED' ? 'bg-green-100 text-green-700 border-green-200' : 'bg-amber-100 text-amber-700 border-amber-200'
                        }`}>{est.status}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mt-2 text-sm text-gray-500">
                        <span>{est.estimation_date}</span>
                        <span>{items.length} item{items.length !== 1 ? 's' : ''}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0 ml-4">
                    <p className="text-xl font-bold text-amber-800">{cur(est.total_net_amount)}</p>
                    <p className="text-xs text-gray-400 mt-1">{isExpanded ? '▲ Collapse' : '▼ View Items'}</p>
                  </div>
                </button>

                {/* Expanded Items */}
                {isExpanded && items.length > 0 && (
                  <div className="border-t border-gray-100 px-6 pb-6">
                    <div className="overflow-x-auto mt-4">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-gray-50 border-b border-gray-100">
                            <th className="px-3 py-2.5 text-left font-semibold text-gray-500 uppercase tracking-wide text-xs">Item</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Qty</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Gross Wt</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Stone Wt</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Net Wt</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Rate/gm</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Purity</th>
                            <th className="px-3 py-2.5 text-right font-semibold text-gray-500 uppercase tracking-wide text-xs">Gross Amt</th>
                            <th className="px-3 py-2.5 text-center font-semibold text-gray-500 uppercase tracking-wide text-xs">Ded %</th>
                            <th className="px-3 py-2.5 text-right font-semibold text-gray-500 uppercase tracking-wide text-xs">Net Amt</th>
                          </tr>
                        </thead>
                        <tbody>
                          {items.map((it, i) => (
                            <tr key={it.estimation_item_id || i} className="border-b border-gray-50">
                              <td className="px-3 py-3 font-medium text-gray-800">{it.item_name}</td>
                              <td className="px-3 py-3 text-center text-gray-600">{it.quantity}</td>
                              <td className="px-3 py-3 text-center text-gray-600">{it.gross_weight_gms}g</td>
                              <td className="px-3 py-3 text-center text-gray-600">{it.stone_weight_gms || 0}g</td>
                              <td className="px-3 py-3 text-center text-gray-600">{it.net_weight_gms}g</td>
                              <td className="px-3 py-3 text-center text-gray-600">{cur(it.gold_rate_per_gm)}</td>
                              <td className="px-3 py-3 text-center text-gray-600">{it.purity_percentage}%</td>
                              <td className="px-3 py-3 text-right text-gray-700">{cur(it.gross_amount)}</td>
                              <td className="px-3 py-3 text-center text-red-600">{it.deduction_percentage}%</td>
                              <td className="px-3 py-3 text-right font-semibold text-gray-800">{cur(it.net_amount)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
