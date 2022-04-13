!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
! Cloud.f90 is a physics module for clouds and hot cores/corinos.                             !  
! If points=1 it models the centre of a spherical cloud with radius rout. For points>1, it    !         
! models a set of evenly distributed positions from rin to rout in a spherical cloud.         !  
!                                                                                             !   
! In order to simulate a molecular cloud, set (phase=1, evap=0)                               !
! Typically, all published uclchem work has a phase1 where we collapse from density of 100 to !
! the inital density of our science model. This gives us initial conditions where the         !
! abundance  of each species is consistent with the network. Set collapse=1 for freefall.     !
!                                                                                             !
! In order to simulate a hot core set (phase=2,evap=1) and the temperature will increase up to!
! maxTemp and will have radial dependence if points>1. Sublimation events take place at certain!
! temperatures following Viti et al. 2004.                                                    !
!                                                                                             !
! Alternatively, set evap=2 to immediately sublimate the ices in the first time step.         !
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
MODULE physics
    USE network
    USE constants
    IMPLICIT NONE
    !Use main loop counters in calculations so they're kept here
    INTEGER :: dstep,points
    !Switches for processes are also here, 1 is on/0 is off.
    INTEGER :: collapse,switch,phase,crDependency

    !evap changes evaporation mode (see chem_evaporate), ion sets c/cx ratio (see initializeChemistry)
    !Flags let physics module control when evap takes place.flag=0/1/2 corresponding to not yet/evaporate/done
    INTEGER :: ion,solidflag,volcflag,coflag,tempindx,instantSublimation

    !variables either controlled by physics or that user may wish to change
    DOUBLE PRECISION :: initialDens,timeInYears,targetTime,currentTime,currentTimeold,finalDens,finalTime,grainRadius,initialTemp
    DOUBLE PRECISION :: cloudSize,rout,rin,baseAv,bc,maxTemp,vs
    
    !variables for the cr ionization dependency
    INTEGER :: ionModel,hDiss, k
    DOUBLE PRECISION :: zSum, ionRate,zeta, zetaScale, dissSum,dissRate,dRate
    
    !Arrays for phase 2 temp profiles. parameters for equation chosen by index
    !arrays go [1Msun,5, 10, 15, 25,60]
    INTEGER, PARAMETER :: nMasses= 6 
    DOUBLE PRECISION,PARAMETER :: tempa(nMasses)=(/1.927d-1,4.8560d-2,7.8470d-3,9.6966d-4,1.706d-4,4.74d-7/)
    DOUBLE PRECISION,PARAMETER :: tempb(nMasses)=(/0.5339,0.6255,0.8395,1.085,1.289,1.98/)
    DOUBLE PRECISION,PARAMETER :: solidtemp(nMasses)=(/20.0,19.6,19.45,19.3,19.5,20.35/)
    DOUBLE PRECISION,PARAMETER :: volctemp(nMasses)=(/84.0,86.3,88.2,89.5,90.4,92.2/)
    DOUBLE PRECISION,PARAMETER :: codestemp(nMasses)=(/95.0,97.5,99.4,100.8,101.6,103.4/)
    DOUBLE PRECISION, allocatable :: av(:),coldens(:),gasTemp(:),dustTemp(:),density(:),monoFracCopy(:)
CONTAINS
!THIS IS WHERE THE REQUIRED PHYSICS ELEMENTS BEGIN.
!YOU CAN CHANGE THEM TO REFLECT YOUR PHYSICS BUT THEY MUST BE NAMED ACCORDINGLY.

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ! Called at start of UCLCHEM run
    ! Uses values in defaultparamters.f90 and any inputs to set initial values        !
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    SUBROUTINE initializePhysics(successFlag)
        INTEGER, INTENT(OUT) :: successFlag
        successFlag=0
        ! Modules not restarted in python wraps so best to reset everything manually.
        IF (ALLOCATED(av)) DEALLOCATE(av,coldens,gasTemp,dustTemp,density,monoFracCopy)
        ALLOCATE(av(points),coldens(points),gasTemp(points),dustTemp(points),density(points),monoFracCopy(size(monoFractions)))
        coFlag=0 !reset sublimation
        solidFlag=0
        volcFlag=0
        monoFracCopy=monoFractions !reset monofractions

        currentTime=0.0
        targetTime=0.0
        timeInYears=0.0

        !Set up basic physics variables
        cloudSize=(rout-rin)*pc
        gasTemp=initialTemp
        dustTemp=gasTemp
        !Set up collapse modes.
        SELECT CASE(collapse)
            !freefall Rawlings 1992
            CASE(0)
                density=initialDens
            CASE(1)
                density=1.001*initialDens
            CASE DEFAULT
                write(*,*) "Collapse must be 0 or 1 for cloud.f90"
        END SELECT

        IF (tempindx .gt. nMasses) THEN
            write(*,*) "tempindx was ",tempindx
            write(*,*) "tempindx must be less than",nMasses
            write(*,*) "1=1Msol, 2=5M, 3=10M, 4=15M, 5=25M, 6=60M"
            successFlag=-1
            RETURN
        END IF 

        !calculate initial column density as distance from core edge to current point * density
        DO dstep=1,points
            coldens(dstep)=real(points-dstep+1)*cloudSize/real(points)*initialDens
        END DO
          !calculate the Av using an assumed extinction outside of core (baseAv), depth of point and density
        av= baseAv +coldens/1.6d21
    END SUBROUTINE

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !Called every time loop in main.f90. Sets the timestep for the next output from   !
    !UCLCHEM. This is also given to the integrator as the targetTime in chemistry.f90 !
    !but the integrator itself chooses an integration timestep.                       !
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    SUBROUTINE updateTargetTime
        IF (timeInYears .gt. 1.0d6) THEN !code in years for readability, targetTime in s
            targetTime=(timeInYears+1.0d5)*SECONDS_PER_YEAR
        ELSE  IF (timeInYears .gt. 1.0d5) THEN
            targetTime=(timeInYears+1.0d4)*SECONDS_PER_YEAR
        ELSE IF (timeInYears .gt. 1.0d4) THEN
            targetTime=(timeInYears+1000.0)*SECONDS_PER_YEAR
        ELSE IF (timeInYears .gt. 1000) THEN
            targetTime=(timeInYears+100.0)*SECONDS_PER_YEAR
        ELSE IF (timeInYears .gt. 0.0) THEN
            targetTime=(timeInYears*10.0)*SECONDS_PER_YEAR
        ELSE
            targetTime=SECONDS_PER_YEAR*1.0d-7
        ENDIF
    END SUBROUTINE updateTargetTime

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !This is called every time/depth step from main.f90                               !
    !Update the density, temperature and av to their values at currentTime            !
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        SUBROUTINE updatePhysics
        !calculate column density. Remember dstep counts from core centre to edge
        !and coldens should be amount of gas from edge to parcel.
        IF (dstep .lt. points) THEN
            !column density of current point + column density of all points further out
            coldens(dstep)=(cloudSize/real(points))*density(dstep)
            coldens(dstep)=coldens(dstep)+sum(coldens(dstep:points))
        ELSE
            coldens(dstep)=cloudSize/real(points)*density(dstep)
        END IF

        !calculate the Av using an assumed extinction outside of core (baseAv), depth of point and density
        av(dstep)= baseAv +coldens(dstep)/1.6d21

        IF (phase .eq. 2 .and. gasTemp(dstep) .lt. maxTemp) THEN
        !Below we include temperature profiles for hot cores, selected using tempindx
        !They are taken from Viti et al. 2004 with an additional distance dependence from Nomura and Millar 2004.
        !It takes the form T=A(t^B)*[(d/R)^-0.5], where A and B are given below for various stellar masses
            gasTemp(dstep)=(cloudSize/(rout*pc))*(real(dstep)/real(points))
            gasTemp(dstep)=gasTemp(dstep)**(-0.5)
            gasTemp(dstep)=initialTemp + ((tempa(tempindx)*(currentTime/SECONDS_PER_YEAR)**tempb(tempindx))*gasTemp(dstep))
            if (gasTemp(dstep) .gt. maxTemp) gasTemp(dstep)=maxTemp
        END IF
        dustTemp=gasTemp
    END SUBROUTINE updatePhysics

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ! This subroutine must be in every physics module.                                !
    ! It receives the abundance array and performs any sublimation related activity   !
    ! In hot core that means following thermalEvaporation subroutine.                 !
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    SUBROUTINE sublimation(abund)
        DOUBLE PRECISION :: abund(nspec+1,points)
        INTENT(INOUT) :: abund
        IF (.not. THREE_PHASE) THEN
            IF (instantSublimation .eq. 1) THEN
                instantSublimation=0
                CALL totalSublimation(abund)
            ELSE IF (coflag .ne. 2) THEN
                IF (gasTemp(dstep) .gt. solidtemp(tempindx) .and. solidflag .ne. 2) solidflag=1
                IF (gasTemp(dstep) .gt. volctemp(tempindx) .and. volcflag .ne. 2) volcflag=1
                IF (gasTemp(dstep) .gt. codestemp(tempindx)) coflag=1
                CALL thermalEvaporation(abund)
            END IF
        END IF
    END SUBROUTINE sublimation

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ! Returns the time derivative of the density.                                     !
    ! Analytical function taken from Rawlings et al. 1992                             !
    ! Called from chemistry.f90, density integrated with abundances so this gives ydot!
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    pure FUNCTION densdot(density)
        DOUBLE PRECISION, INTENT(IN) :: density
        DOUBLE PRECISION :: densdot
        !Rawlings et al. 1992 freefall collapse. With factor bc for B-field etc
        IF (density .lt. finalDens) THEN
             densdot=bc*(density**4./initialDens)**0.33*&
             &(8.4d-30*initialDens*((density/initialDens)**0.33-1.))**0.5
        ELSE
            densdot=0.0
        ENDIF
    END FUNCTION densdot

    pure FUNCTION dByDnDensdot(density)
    DOUBLE PRECISION, INTENT(IN) :: density
    DOUBLE PRECISION :: dByDnDensdot
    !Rawlings et al. 1992 freefall collapse. With factor bc for B-field etc
    IF (density .lt. finalDens) THEN
        dByDndensdot=bc*8.4d-30*(density**3)*((9.0d0*((density/initialDens)**0.33))-8.0d0)
        dByDnDensdot=dByDnDensdot/(6.0d0*(((density**4.0)/initialDens)**0.66))
        dByDnDensdot=dByDnDensdot/dsqrt(initialDens*8.4d-30*(((density/initialDens)**0.33))-1.0d0)
    ELSE
        dByDnDensdot=0.0
    ENDIF
    END FUNCTION dByDnDensdot

    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    !REQUIRED PHYSICS ENDS HERE, ANY ADDITIONAL PHYSICS CAN BE ADDED BELOW.
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    SUBROUTINE thermalEvaporation(abund)
    DOUBLE PRECISION :: abund(nspec+1,points)
    INTENT(INOUT) :: abund
    !Evaporation is based on Viti et al. 2004. A proportion of the frozen species is released into the gas phase
    !in specific events. These events are activated by flags (eg solidflag) which can be set in physics module.
    !The species evaporated are in lists, created by Makerates and based on groupings. see the viti 2004 paper.
        IF (sum(abund(iceList,dstep)) .gt. 1d-30) THEN
            !Solid Evap
            IF (solidflag .eq. 1) THEN
                CALL partialSublimation(solidFractions,abund)
                solidflag=2
            ENDIF

            !monotonic evaporation at binding energy of species
            CALL bindingEnergyEvap(abund)

            !Volcanic evap
            IF (volcflag .eq. 1) THEN
                CALL partialSublimation(volcanicFractions,abund)
                volcflag=2 !Set flag to 2 to stop it being recalled
            ENDIF

            !Co-desorption
            IF (coflag .eq. 1) THEN
                CALL totalSublimation(abund)
                coflag=2
            ENDIF
        ENDIF
    END SUBROUTINE thermalEvaporation

    SUBROUTINE partialSublimation(fractions, abund)
        DOUBLE PRECISION :: abund(nspec+1,points)
        DOUBLE PRECISION :: fractions(:)

        abund(gasiceList,dstep)=abund(gasiceList,dstep)+fractions*abund(iceList,dstep)
        abund(iceList,dstep)=(1.0-fractions)*abund(iceList,dstep)

    END SUBROUTINE partialSublimation

    SUBROUTINE totalSublimation(abund)
        DOUBLE PRECISION :: abund(nspec+1,points)
        abund(gasiceList,dstep)=abund(gasiceList,dstep)+abund(iceList,dstep)
        abund(iceList,dstep)=1d-30
    END SUBROUTINE totalSublimation

    SUBROUTINE bindingEnergyEvap(abund)
        DOUBLE PRECISION :: abund(nspec+1,points)
        double precision, parameter :: SURFACE_SITE_DENSITY = 1.5d15
        INTENT(INOUT) :: abund
        INTEGER :: i
        !Subroutine to handle mono-evaporation. See viti 2004
        double precision en,newm,expdust,freq,kevap
        integer speci
        !mono evaporation at the binding energy of each species
        DO i=lbound(iceList,1),ubound(iceList,1)
            speci=iceList(i)
            en=bindingEnergy(i)*K_BOLTZ_SI
            expdust=bindingEnergy(i)/gasTemp(dstep)
            newm = mass(speci)*1.66053e-27
            freq = dsqrt((2*(SURFACE_SITE_DENSITY)*en)/((pi**2)*newm))
            kevap=freq*exp(-expdust)
            IF (kevap .ge. 0.99) THEN
                abund(gasiceList(i),dstep)=abund(gasiceList(i),dstep)+(monoFracCopy(i)*abund(speci,dstep))
                abund(speci,dstep)=(1.0-monoFracCopy(i))*abund(speci,dstep)
                monoFracCopy(i)=0.0
            END IF 
        END DO
    END SUBROUTINE bindingEnergyEvap

    SUBROUTINE ionizationDependency
        !Arrays fopr calculating rates
        !ckLIon and ckHIon are the coefficients for the cosmic ray ionization rate
        !ckLDiss and ckHDiss are the coefficients for the H2 dissociation rate
        !if ionModel = 0 use the L model coefficients, if = 1 use the H model
        DOUBLE PRECISION,PARAMETER :: ckLIon(10)=(/1.545456645800d7, -6.307708626617d6, 1.142680666041d6, -1.205932302621d5,&
                                                8.170913352693d3, -3.686121296079d2,1.107203722057d1, -2.135293914267d-1,&
                                                2.399219033781d-3, -1.196664901916d-5/)
        DOUBLE PRECISION, PARAMETER :: ckLDiss(10)=(/1.582911005330d7,-6.465722684896d6, 1.172189025424d6, -1.237950798073d5, &
                                                8.393404654312d3, -3.788811358130d2, 1.138688455029d1, -2.197136304567d-1, &
                                                2.469841278950d-3, -1.232393620924d-5/)
        DOUBLE PRECISION,PARAMETER :: ckHIon(10)=(/1.223529865309d7, -5.013766644305d6, 9.120125566763d5, -9.665446168847d4,&
                                                6.576930812109d3, -2.979875686226d2,8.989721355058d0, -1.741300519598d-1,&
                                                1.965098116126d-3, -9.844203439473d-6/)
        DOUBLE PRECISION, PARAMETER :: ckHDiss(10)=(/1.217227462831d7,-4.989649250304d6, 9.079152156645d5, -9.624890825395d4, &
                                                6.551161486120d3, -2.968976216187d2, 8.959037875226d0, -1.735757324445d-1, &
                                                1.959267277734d-3, -9.816996707980d-6/)
        
        zeta= 1.0
        zSum = 0
        DO k=0,9,1
            IF (ionModel .eq. 0) THEN
                ionRate=ckLIon(k+1)*log10(coldens(dstep))**k
            ELSEIF (ionModel .eq. 1) THEN
                ionRate=ckHIon(k+1)*log10(coldens(dstep))**k
            ELSE 
                write(*,*) "WARNING: ionModel switch must be 0 or 1"
            ENDIF
            zSum=zSum+ionRate
        END DO

        zeta=((10**zSum)/1.3d-17)* zetaScale

        !rate calculation for H2 dissociation
        IF (hDiss .eq. 1) THEN
            dissSum = 0
            DO k=0,9,1
                IF (ionModel .eq. 0) THEN
                    dRate=ckLDiss(k+1)*log10(coldens(dstep))**k
                ELSEIF (ionModel .eq. 1) THEN
                    dRate=ckHDiss(k+1)*log10(coldens(dstep))**k
                ELSE 
                    write(*,*) "WARNING: ionModel switch must be 0 or 1"
                ENDIF
                dissSum=dissSum+dRate
            END DO
            dissRate=(10**dissSum)*zetaScale
        END IF
    
    END SUBROUTINE ionizationDependency

    
END MODULE physics


